from __future__ import annotations

import hashlib
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone, date
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from decimal import Decimal
from dndn_worker.s3_uploader import upload_tree_to_s3

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from jsonschema import Draft202012Validator

try:
    # Python 3.9+
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None  # type: ignore


KST_TZ = "Asia/Seoul"


@dataclass(frozen=True)
class WorkerExecutionResult:
    # TODO: 플랫폼 상태 저장소를 붙일 때 contracts/job_status.schema.json과
    # 이 런타임 결과 모델을 맞춰야 함. status, executor_id,
    # requested_at, started_at, finished_at 필드는 후속 PR에서 반영 예정.
    run_id: str
    result_path: Path
    job_type: str
    retryable: bool = False
    already_processed: bool = False
    error_code: Optional[str] = None

    @property
    def succeeded(self) -> bool:
        return self.error_code is None


class WorkerExecutionError(Exception):
    def __init__(self, error_code: str, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.retryable = retryable

    def __str__(self) -> str:
        return f"{self.error_code}: {super().__str__()}"


def _json_default(o):
    # CloudTrail EventTime 같은 datetime 대응
    if isinstance(o, (datetime, date)):
        # 2026-03-04T01:23:45Z 같은 형태로 남기고 싶으면 +00:00 -> Z 치환
        return o.isoformat().replace("+00:00", "Z")
    # Cost Explorer 등 붙이면 Decimal 튀어나올 수 있어서 미리 대응
    if isinstance(o, Decimal):
        return float(o)
    return str(o)

def _now_kst() -> datetime:
    if ZoneInfo is None:
        # Fallback: fixed +09:00
        return datetime.now(timezone(timedelta(hours=9)))
    return datetime.now(ZoneInfo(KST_TZ))


def _to_kst_iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    if ZoneInfo is None:
        kst = dt.astimezone(timezone(timedelta(hours=9)))
    else:
        kst = dt.astimezone(ZoneInfo(KST_TZ))
    # Keep seconds (deterministic-ish)
    return kst.replace(microsecond=0).isoformat()


def _parse_dt(s: str) -> datetime:
    # Python supports "+09:00" and "Z"
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def dump_json(path, obj):
    path.write_text(
        json.dumps(obj, ensure_ascii=False, indent=2, default=_json_default),
        encoding="utf-8",
    )


def dump_jsonl(path: Path, rows: Iterable[Dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False, default=_json_default))
            f.write("\n")


def validate_with_schema(instance: Any, schema_path: Path) -> None:
    schema = load_json(schema_path)
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(instance), key=lambda e: e.path)
    if errors:
        msgs = []
        for e in errors[:10]:
            loc = ".".join([str(x) for x in e.absolute_path]) or "<root>"
            msgs.append(f"- {loc}: {e.message}")
        raise ValueError("Schema validation failed:\n" + "\n".join(msgs))


def _client_error_code(e: ClientError) -> str:
    return e.response.get("Error", {}).get("Code", "Unknown")


def _stage_ok() -> Dict[str, Any]:
    return {"status": "OK"}


def _stage_na(reason: str, message: str) -> Dict[str, Any]:
    # reason must be one of contracts/$defs/na_reason_enum
    return {"status": "NA", "na_reason": reason, "message": message}


def _stage_failed(code: str, message: str, retryable: bool = False) -> Dict[str, Any]:
    return {"status": "FAILED", "error_code": code, "message": message, "retryable": retryable}


def _role_session_name(run_id: str) -> str:
    return f"dndn-{run_id}"[:64]


def assume_role_session(
    role_arn: str,
    external_id: str,
    base_session: Optional[boto3.Session] = None,
    *,
    run_id: Optional[str] = None,
) -> boto3.Session:
    """
    Production path: use STS AssumeRole.
    Dev shortcut: if role_arn == 'SELF', return default/base session.
    """
    if role_arn.strip().upper() == "SELF":
        return base_session or boto3.Session()

    sts_session = base_session or boto3.Session()
    sts = sts_session.client("sts")

    session_name = _role_session_name(
        run_id or ("run-" + _sha256_bytes(os.urandom(16))[:12])
    )

    resp = sts.assume_role(
        RoleArn=role_arn,
        RoleSessionName=session_name,
        ExternalId=external_id,
    )
    c = resp["Credentials"]
    return boto3.Session(
        aws_access_key_id=c["AccessKeyId"],
        aws_secret_access_key=c["SecretAccessKey"],
        aws_session_token=c["SessionToken"],
    )


def resolve_time_range(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Returns contracts/$defs/time_range dict: {start,end,timezone[,note]}
    - WEEKLY: use payload.time_range
    - EVENT: compute from payload.event_time ± window_minutes
    """
    job_type = payload["type"]
    if job_type == "WEEKLY":
        tr = payload["time_range"]
        return {
            "start": tr["start"],
            "end": tr["end"],
            "timezone": tr.get("timezone", KST_TZ),
        }

    # EVENT
    event_time = _parse_dt(payload["event_time"])
    window = int(payload["window_minutes"])
    start = event_time - timedelta(minutes=window)
    end = event_time + timedelta(minutes=window)
    tz = KST_TZ
    return {
        "start": _to_kst_iso(start),
        "end": _to_kst_iso(end),
        "timezone": tz,
        "note": f"event_time ± {window}m",
    }


def build_partition(payload: Dict[str, Any], time_range: Dict[str, Any]) -> Dict[str, int]:
    job_type = payload["type"]
    if job_type == "WEEKLY":
        start = _parse_dt(time_range["start"])
        # Use ISO week number in KST
        if ZoneInfo is not None:
            start = start.astimezone(ZoneInfo(KST_TZ))
        iso_year, iso_week, _ = start.isocalendar()
        return {"year": int(iso_year), "week": int(iso_week)}

    # EVENT: partition by event date
    event_time = _parse_dt(payload["event_time"])
    if ZoneInfo is not None:
        event_time = event_time.astimezone(ZoneInfo(KST_TZ))
    return {"year": event_time.year, "month": event_time.month, "day": event_time.day}


def _s3_uri(bucket: str, key: str) -> str:
    key = key.lstrip("/")
    return f"s3://{bucket}/{key}"


def _evidence_uris(payload: Dict[str, Any]) -> Dict[str, Any]:
    bucket = payload["s3"]["bucket"]
    prefix = payload["s3"]["prefix"].rstrip("/")
    raw_prefix = _s3_uri(bucket, f"{prefix}/raw/")
    norm_prefix = _s3_uri(bucket, f"{prefix}/normalized/")
    # Optional: where the job payload itself was stored
    job_payload_uri = _s3_uri(bucket, f"{prefix}/raw/meta/job_payload.json")
    index_uri = _s3_uri(bucket, f"{prefix}/raw/index.json")
    return {
        "raw_prefix_s3_uri": raw_prefix,
        "normalized_prefix_s3_uri": norm_prefix,
        "job_payload_s3_uri": job_payload_uri,
        "index_s3_uri": index_uri,
    }


def collect_cloudtrail_lookup_events(
    session: boto3.Session,
    regions: List[str],
    start: datetime,
    end: datetime,
    max_events: int = 500,
) -> List[Dict[str, Any]]:
    all_events: List[Dict[str, Any]] = []
    for region in regions:
        ct = session.client("cloudtrail", region_name=region)
        token = None
        while True:
            kwargs: Dict[str, Any] = {"StartTime": start, "EndTime": end, "MaxResults": 50}
            if token:
                kwargs["NextToken"] = token
            resp = ct.lookup_events(**kwargs)
            for e in resp.get("Events", []):
                # Annotate region for convenience
                e["AwsRegion"] = e.get("AwsRegion") or region
                all_events.append(e)
                if len(all_events) >= max_events:
                    return all_events
            token = resp.get("NextToken")
            if not token:
                break
    return all_events


def detect_config_enabled(session: boto3.Session, region: str) -> Tuple[bool, str]:
    """
    Returns (enabled, message). 'enabled' means a configuration recorder exists.
    """
    cfg = session.client("config", region_name=region)
    resp = cfg.describe_configuration_recorders()
    recs = resp.get("ConfigurationRecorders", [])
    if not recs:
        return False, "AWS Config recorder is not enabled in this region"
    return True, "AWS Config recorder detected"


def _safe_fs_name(value: str) -> str:
    return "".join(c if c.isalnum() or c in ("-", "_", ".") else "_" for c in value)


def _parse_event_time_for_config(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = _parse_dt(value)
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _serialize_config_item(item: Dict[str, Any]) -> Dict[str, Any]:
    serialized: Dict[str, Any] = {
        "capture_time": _to_kst_iso(item["configurationItemCaptureTime"])
        if isinstance(item.get("configurationItemCaptureTime"), datetime)
        else None,
        "resource_type": item.get("resourceType"),
        "resource_id": item.get("resourceId"),
        "resource_name": item.get("resourceName"),
        "arn": item.get("arn"),
        "configuration_item_status": item.get("configurationItemStatus"),
    }

    configuration = item.get("configuration")
    if isinstance(configuration, str):
        try:
            configuration = json.loads(configuration)
        except Exception:
            pass
    serialized["configuration"] = configuration

    supplementary = item.get("supplementaryConfiguration")
    if isinstance(supplementary, str):
        try:
            supplementary = json.loads(supplementary)
        except Exception:
            pass
    if supplementary is not None:
        serialized["supplementary_configuration"] = supplementary

    for key in ("tags", "relationships", "accountId", "awsRegion", "availabilityZone", "version"):
        if key in item:
            serialized[key] = item.get(key)

    return {k: v for k, v in serialized.items() if v is not None}


def _get_single_config_history_page(
    session: boto3.Session,
    region: str,
    resource_type: str,
    resource_id: str,
    *,
    earlier_time: Optional[datetime] = None,
    later_time: Optional[datetime] = None,
    chronological_order: str = "Reverse",
    limit: int = 10,
) -> List[Dict[str, Any]]:
    cfg = session.client("config", region_name=region)
    kwargs: Dict[str, Any] = {
        "resourceType": resource_type,
        "resourceId": resource_id,
        "chronologicalOrder": chronological_order,
        "limit": limit,
    }
    if earlier_time is not None:
        kwargs["earlierTime"] = earlier_time
    if later_time is not None:
        kwargs["laterTime"] = later_time
    resp = cfg.get_resource_config_history(**kwargs)
    return resp.get("configurationItems", []) or []


def get_config_before_after_best_effort(
    session: boto3.Session,
    region: str,
    resource_type: str,
    resource_id: str,
    event_time: datetime,
) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]], Dict[str, List[Dict[str, Any]]]]:
    before_items = _get_single_config_history_page(
        session=session,
        region=region,
        resource_type=resource_type,
        resource_id=resource_id,
        earlier_time=event_time,
        chronological_order="Reverse",
        limit=5,
    )
    after_items = _get_single_config_history_page(
        session=session,
        region=region,
        resource_type=resource_type,
        resource_id=resource_id,
        later_time=event_time,
        chronological_order="Forward",
        limit=5,
    )

    before_raw = before_items[0] if before_items else None
    after_raw = after_items[0] if after_items else None

    before = _serialize_config_item(before_raw) if before_raw else None
    after = _serialize_config_item(after_raw) if after_raw else None
    raw_bundle = {
        "before_items": [_serialize_config_item(i) for i in before_items],
        "after_items": [_serialize_config_item(i) for i in after_items],
    }
    return before, after, raw_bundle


def _write_config_snapshot_artifacts(
    raw_dir: Path,
    payload: Dict[str, Any],
    resource_key: str,
    before: Optional[Dict[str, Any]],
    after: Optional[Dict[str, Any]],
    raw_bundle: Dict[str, List[Dict[str, Any]]],
) -> Dict[str, Optional[str]]:
    bucket = payload["s3"]["bucket"]
    prefix = payload["s3"]["prefix"].rstrip("/")
    safe_key = _safe_fs_name(resource_key)
    base_dir = raw_dir / "config" / safe_key
    _ensure_dir(base_dir)

    uris: Dict[str, Optional[str]] = {
        "before_s3_uri": None,
        "after_s3_uri": None,
        "history_s3_uri": None,
    }

    history_path = base_dir / "history.json"
    dump_json(history_path, raw_bundle)
    uris["history_s3_uri"] = _s3_uri(bucket, f"{prefix}/raw/config/{safe_key}/history.json")

    if before is not None:
        before_path = base_dir / "before.json"
        dump_json(before_path, before)
        uris["before_s3_uri"] = _s3_uri(bucket, f"{prefix}/raw/config/{safe_key}/before.json")

    if after is not None:
        after_path = base_dir / "after.json"
        dump_json(after_path, after)
        uris["after_s3_uri"] = _s3_uri(bucket, f"{prefix}/raw/config/{safe_key}/after.json")

    return uris


def _trigger_artifact_filename(trigger: Dict[str, Any]) -> str:
    detail_type = str(trigger.get("detail_type") or "")
    logical_source = str(
        trigger.get("logical_source")
        or trigger.get("origin_kind")
        or trigger.get("upstream_source")
        or trigger.get("source")
        or ""
    ).upper()

    if detail_type == "AWS Health Event" or logical_source == "AWS_HEALTH":
        return "aws_health_event.json"
    if detail_type == "Security Hub Findings - Imported" or logical_source == "SECURITYHUB":
        return "securityhub_finding.json"
    if logical_source in {"MANUAL", "API"}:
        return "manual_trigger.json"
    return "eventbridge.json"


def _trigger_artifact_payload(trigger: Dict[str, Any]) -> Optional[Any]:
    for key in ("raw_event", "event", "detail", "finding", "health"):
        value = trigger.get(key)
        if value is not None:
            return value
    if trigger:
        return trigger
    return None


def _write_trigger_artifact(
    raw_dir: Path,
    payload: Dict[str, Any],
) -> Optional[str]:
    if payload.get("type") != "EVENT":
        return None

    trigger = payload.get("trigger")
    if not isinstance(trigger, dict):
        return None

    artifact_payload = _trigger_artifact_payload(trigger)
    if artifact_payload is None:
        return None

    trigger_dir = raw_dir / "trigger"
    _ensure_dir(trigger_dir)

    filename = _trigger_artifact_filename(trigger)
    path = trigger_dir / filename
    dump_json(path, artifact_payload)

    bucket = payload["s3"]["bucket"]
    prefix = payload["s3"]["prefix"].rstrip("/")
    return _s3_uri(bucket, f"{prefix}/raw/trigger/{filename}")


def _artifact_kind_from_path(rel_path: str) -> str:
    parts = rel_path.split("/")
    if rel_path == "raw/index.json":
        return "artifact_index"
    if rel_path == "raw/meta/job_payload.json":
        return "job_payload"
    if parts[:2] == ["raw", "trigger"]:
        return "trigger"
    if parts[:2] == ["raw", "cloudtrail"]:
        return "cloudtrail_lookup" if rel_path.endswith("lookup_events.jsonl") else "cloudtrail_event"
    if parts[:2] == ["raw", "config"]:
        return "config_snapshot"
    if parts[:2] == ["raw", "advisor"]:
        return "advisor_raw"
    if parts[:2] == ["normalized"]:
        return "normalized_result"
    return "artifact"


def _write_artifact_index(job_dir: Path, payload: Dict[str, Any]) -> Path:
    bucket = payload["s3"]["bucket"]
    prefix = payload["s3"]["prefix"].strip("/")

    files: List[Dict[str, Any]] = []
    for p in sorted(job_dir.rglob("*")):
        if p.is_dir():
            continue
        if p.name == ".DS_Store" or p.name.startswith("._"):
            continue
        rel = p.relative_to(job_dir).as_posix()
        files.append(
            {
                "category": rel.split("/", 1)[0],
                "kind": _artifact_kind_from_path(rel),
                "path": rel,
                "s3_uri": _s3_uri(bucket, f"{prefix}/{rel}" if prefix else rel),
            }
        )

    index_rel = "raw/index.json"
    files.append(
        {
            "category": "raw",
            "kind": "artifact_index",
            "path": index_rel,
            "s3_uri": _s3_uri(bucket, f"{prefix}/{index_rel}" if prefix else index_rel),
        }
    )

    index_doc = {
        "run_id": payload.get("run_id"),
        "type": payload.get("type"),
        "bucket": bucket,
        "prefix": prefix,
        "files": files,
    }

    index_path = job_dir / index_rel
    _ensure_dir(index_path.parent)
    dump_json(index_path, index_doc)
    return index_path


def enrich_resources_with_config(
    session: boto3.Session,
    resources: List[Dict[str, Any]],
    payload: Dict[str, Any],
    raw_dir: Path,
    collection_status: Dict[str, Any],
) -> None:
    cfg_status = collection_status.get("config", {})

    if cfg_status.get("status") == "NA":
        for g in resources:
            g["config"] = {
                "status": "NA",
                "na_reason": cfg_status.get("na_reason", "UNKNOWN"),
                "message": cfg_status.get("message", "Config not available"),
            }
        return

    if cfg_status.get("status") == "FAILED":
        for g in resources:
            g["config"] = {
                "status": "FAILED",
                "error_code": cfg_status.get("error_code", "CONFIG_DESCRIBE_FAILED"),
                "message": cfg_status.get("message", "Config stage failed before enrichment"),
            }
        return

    if cfg_status.get("status") != "OK":
        for g in resources:
            g["config"] = {
                "status": "NA",
                "na_reason": "UNKNOWN",
                "message": "Config stage did not complete successfully",
            }
        return

    for g in resources:
        resource = g.get("resource") or {}
        region = resource.get("region")
        resource_type = resource.get("resource_type")
        resource_id = resource.get("resource_id")
        event_time = _parse_event_time_for_config((g.get("change_summary") or {}).get("last_event_time"))

        if not region or not resource_type or not resource_id:
            g["config"] = {
                "status": "NA",
                "na_reason": "NO_DATA",
                "message": "Resource is missing region/resource_type/resource_id for Config lookup",
            }
            continue

        if event_time is None:
            g["config"] = {
                "status": "NA",
                "na_reason": "NO_DATA",
                "message": "No event_time available to anchor Config before/after lookup",
            }
            continue

        try:
            before, after, raw_bundle = get_config_before_after_best_effort(
                session=session,
                region=region,
                resource_type=resource_type,
                resource_id=resource_id,
                event_time=event_time,
            )
        except ClientError as e:
            code = _client_error_code(e)
            if code in ("AccessDenied", "AccessDeniedException", "UnauthorizedOperation"):
                g["config"] = {
                    "status": "NA",
                    "na_reason": "PERMISSION_DENIED",
                    "message": f"{code}: {e}",
                }
            else:
                g["config"] = {
                    "status": "FAILED",
                    "error_code": "CONFIG_HISTORY_FAILED",
                    "message": f"{code}: {e}",
                }
            continue
        except Exception as e:
            g["config"] = {
                "status": "FAILED",
                "error_code": "CONFIG_HISTORY_FAILED",
                "message": str(e),
            }
            continue

        if before is None and after is None:
            g["config"] = {
                "status": "NA",
                "na_reason": "NO_DATA",
                "message": "No Config history found for this resource around the event time",
                "collected_at": _to_kst_iso(_now_kst()),
            }
            continue

        uris = _write_config_snapshot_artifacts(
            raw_dir=raw_dir,
            payload=payload,
            resource_key=g["key"],
            before=before,
            after=after,
            raw_bundle=raw_bundle,
        )
        extensions: Dict[str, Any] = {}
        if uris.get("history_s3_uri"):
            extensions["history_s3_uri"] = uris["history_s3_uri"]

        g["config"] = {
            "status": "OK",
            "before": before,
            "after": after,
            "before_s3_uri": uris.get("before_s3_uri"),
            "after_s3_uri": uris.get("after_s3_uri"),
            "collected_at": _to_kst_iso(_now_kst()),
            "extensions": extensions,
        }



AWS_HEALTH_TERRAFORM_SERVICES = {
    "EC2",
    "EKS",
    "RDS",
    "ELASTICLOADBALANCING",
    "ELB",
    "AUTOSCALING",
    "AUTO_SCALING",
    "DYNAMODB",
}


def _transport_source_for_meta(trigger_source: Any) -> str:
    value = str(trigger_source or "EVENTBRIDGE").upper()
    allowed = {"EVENTBRIDGE", "SQS", "CRONJOB", "MANUAL", "API", "SCHEDULER"}
    return value if value in allowed else "EVENTBRIDGE"


def _event_origin_kind(payload: Dict[str, Any]) -> str:
    trig = payload.get("trigger") or {}
    explicit = trig.get("logical_source") or trig.get("origin_kind") or trig.get("upstream_source")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip().upper()

    detail_type = str(trig.get("detail_type") or "")
    if detail_type == "AWS Health Event":
        return "AWS_HEALTH"
    if detail_type == "Security Hub Findings - Imported" or trig.get("finding") or trig.get("finding_arn"):
        return "SECURITYHUB"
    if str(trig.get("source") or "").upper() == "MANUAL":
        return "MANUAL"
    return "UNKNOWN"


def _extract_arn_resource_info(arn: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    try:
        parts = arn.split(":", 5)
        if len(parts) < 6 or parts[0] != "arn":
            return None, None, None
        service = parts[2]
        region = parts[3] or None
        resource = parts[5]

        if service == "ec2":
            if resource.startswith("instance/"):
                return "AWS::EC2::Instance", resource.split("/", 1)[1], region
            if resource.startswith("security-group/"):
                return "AWS::EC2::SecurityGroup", resource.split("/", 1)[1], region
            if resource.startswith("volume/"):
                return "AWS::EC2::Volume", resource.split("/", 1)[1], region
            if resource.startswith("network-interface/"):
                return "AWS::EC2::NetworkInterface", resource.split("/", 1)[1], region
        if service == "s3":
            return "AWS::S3::Bucket", resource, region
        if service == "rds":
            if resource.startswith("db:"):
                return "AWS::RDS::DBInstance", resource.split(":", 1)[1], region
        if service == "eks":
            if resource.startswith("cluster/"):
                return "AWS::EKS::Cluster", resource.split("/", 1)[1], region
            if resource.startswith("nodegroup/"):
                return "AWS::EKS::Nodegroup", resource.split("/", 1)[1], region
        if service == "elasticloadbalancing":
            return "AWS::ElasticLoadBalancingV2::LoadBalancer", resource, region
    except Exception:
        pass
    return None, None, None


def _service_hint_upper(detail: Dict[str, Any]) -> str:
    service = str(detail.get("service") or "").upper()
    if service:
        return service
    event_type_code = str(detail.get("eventTypeCode") or "")
    if event_type_code.startswith("AWS_"):
        parts = event_type_code.split("_")
        if len(parts) >= 2:
            return parts[1].upper()
    return ""


def _infer_resource_from_identifier(identifier: str, region: str, service_hint: str = "") -> Optional[Dict[str, Any]]:
    if not identifier:
        return None
    if identifier.startswith("arn:"):
        r_type, r_id, r_region = _extract_arn_resource_info(identifier)
        if r_type and r_id:
            ref = {"resource_type": r_type, "resource_id": r_id}
            if region or r_region:
                ref["region"] = r_region or region
            ref["arn"] = identifier
            return ref

    service_hint = service_hint.upper()
    known_prefixes = {
        "i-": "AWS::EC2::Instance",
        "sg-": "AWS::EC2::SecurityGroup",
        "vol-": "AWS::EC2::Volume",
        "eni-": "AWS::EC2::NetworkInterface",
        "snap-": "AWS::EC2::Snapshot",
        "eipalloc-": "AWS::EC2::EIP",
        "subnet-": "AWS::EC2::Subnet",
        "vpc-": "AWS::EC2::VPC",
        "igw-": "AWS::EC2::InternetGateway",
        "rtb-": "AWS::EC2::RouteTable",
    }
    for prefix, r_type in known_prefixes.items():
        if identifier.startswith(prefix):
            return {"resource_type": r_type, "resource_id": identifier, "region": region}

    if service_hint == "EKS":
        return {"resource_type": "AWS::EKS::Cluster", "resource_id": identifier, "region": region}
    if service_hint == "RDS":
        return {"resource_type": "AWS::RDS::DBInstance", "resource_id": identifier, "region": region}
    if service_hint in {"ELASTICLOADBALANCING", "ELB"}:
        return {"resource_type": "AWS::ElasticLoadBalancingV2::LoadBalancer", "resource_id": identifier, "region": region}

    return None


def _extract_hint_resource_refs(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    hint_res = (payload.get("hint") or {}).get("resource")
    if not isinstance(hint_res, dict):
        return []
    if not hint_res.get("resource_type") or not hint_res.get("resource_id"):
        return []
    ref = {
        "resource_type": hint_res["resource_type"],
        "resource_id": hint_res["resource_id"],
        "account_id": payload.get("account_id"),
        "region": hint_res.get("region") or (payload.get("regions") or [""])[0],
    }
    if hint_res.get("arn"):
        ref["arn"] = hint_res["arn"]
    return [ref]


def _extract_securityhub_resource_refs(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    trig = payload.get("trigger") or {}
    finding = trig.get("finding") or {}
    if not isinstance(finding, dict):
        return []
    refs: List[Dict[str, Any]] = []
    for r in finding.get("Resources", []) or []:
        if not isinstance(r, dict):
            continue
        identifier = r.get("Id") or ""
        region = r.get("Region") or (payload.get("regions") or [""])[0]
        ref = None
        if identifier.startswith("arn:"):
            r_type, r_id, r_region = _extract_arn_resource_info(identifier)
            if r_type and r_id:
                ref = {"resource_type": r_type, "resource_id": r_id, "region": r_region or region, "arn": identifier}
        if ref is None and r.get("Type"):
            ref = {
                "resource_type": str(r.get("Type")),
                "resource_id": identifier or str(r.get("Type")),
                "region": region,
            }
            if identifier.startswith("arn:"):
                ref["arn"] = identifier
        if ref:
            ref["account_id"] = payload.get("account_id")
            refs.append(ref)
    return refs


def _extract_aws_health_resource_refs(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    trig = payload.get("trigger") or {}
    health = trig.get("health") or trig.get("detail") or {}
    if not isinstance(health, dict):
        return []
    region = health.get("eventRegion") or (payload.get("regions") or [""])[0]
    service_hint = _service_hint_upper(health)
    refs: List[Dict[str, Any]] = []

    for arn in trig.get("resources", []) or []:
        if isinstance(arn, str) and arn:
            ref = _infer_resource_from_identifier(arn, region=region, service_hint=service_hint)
            if ref:
                ref["account_id"] = payload.get("account_id")
                refs.append(ref)

    for ent in health.get("affectedEntities", []) or []:
        if not isinstance(ent, dict):
            continue
        identifier = ent.get("entityValue") or ent.get("entityArn") or ""
        ref = _infer_resource_from_identifier(identifier, region=region, service_hint=service_hint)
        if ref:
            ref["account_id"] = payload.get("account_id")
            refs.append(ref)

    dedup: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    for ref in refs:
        key = (str(ref.get("region") or ""), str(ref["resource_type"]), str(ref["resource_id"]))
        dedup[key] = _merge_resource_ref(dedup.get(key), ref)
    return list(dedup.values())


def _extract_trigger_resource_refs(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    refs: List[Dict[str, Any]] = []
    refs.extend(_extract_hint_resource_refs(payload))

    kind = _event_origin_kind(payload)
    if kind == "SECURITYHUB":
        refs.extend(_extract_securityhub_resource_refs(payload))
    elif kind == "AWS_HEALTH":
        refs.extend(_extract_aws_health_resource_refs(payload))

    dedup: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    for ref in refs:
        key = (str(ref.get("region") or ""), str(ref["resource_type"]), str(ref["resource_id"]))
        dedup[key] = _merge_resource_ref(dedup.get(key), ref)
    return list(dedup.values())


def _merge_resource_ref(existing: Optional[Dict[str, Any]], incoming: Dict[str, Any]) -> Dict[str, Any]:
    if existing is None:
        return dict(incoming)

    merged = dict(existing)
    for field in ("resource_type", "resource_id", "region", "arn", "account_id"):
        if not merged.get(field) and incoming.get(field):
            merged[field] = incoming[field]
    return merged


def _resource_group_from_ref(ref: Dict[str, Any]) -> Dict[str, Any]:
    region = ref.get("region") or ""
    key = f"{region}:{ref['resource_type']}:{ref['resource_id']}"
    resource_ref = {
        "resource_type": ref["resource_type"],
        "resource_id": ref["resource_id"],
    }
    if ref.get("arn"):
        resource_ref["arn"] = ref["arn"]
    if ref.get("account_id"):
        resource_ref["account_id"] = ref["account_id"]
    if region:
        resource_ref["region"] = region
    return {
        "key": key,
        "resource": resource_ref,
        "events": [],
    }


def merge_resource_groups_with_trigger_refs(
    resources: List[Dict[str, Any]],
    extra_refs: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    groups: Dict[str, Dict[str, Any]] = {g["key"]: g for g in resources}
    for ref in extra_refs:
        incoming_group = _resource_group_from_ref(ref)
        existing_group = groups.get(incoming_group["key"])
        if existing_group is None:
            groups[incoming_group["key"]] = incoming_group
            continue
        existing_group["resource"] = _merge_resource_ref(existing_group.get("resource"), incoming_group["resource"])
    out = list(groups.values())
    out.sort(key=lambda x: x["key"])
    return out


def _build_securityhub_extensions(payload: Dict[str, Any]) -> Dict[str, Any]:
    trig = payload.get("trigger") or {}
    finding = trig.get("finding") or {}
    if not isinstance(finding, dict):
        return {}
    sev = finding.get("Severity")
    if isinstance(sev, dict):
        sev_obj = {
            "label": sev.get("Label"),
            "normalized": sev.get("Normalized"),
        }
    else:
        sev_obj = {"label": sev} if sev else None
    if isinstance(sev_obj, dict):
        sev_obj = {k: v for k, v in sev_obj.items() if v is not None}

    comp = finding.get("Compliance")
    compliance = None
    if isinstance(comp, dict):
        compliance = {
            "status": comp.get("Status"),
            "standards_control_arn": comp.get("RelatedRequirements", [None])[0]
            if isinstance(comp.get("RelatedRequirements"), list)
            and comp.get("RelatedRequirements")
            else comp.get("StandardsControlArn"),
        }
        compliance = {k: v for k, v in compliance.items() if v is not None}

    rem = finding.get("Remediation")
    remediation = None
    if isinstance(rem, dict):
        rec = rem.get("Recommendation")
        if isinstance(rec, dict):
            remediation = {
                "text": rec.get("Text"),
                "url": rec.get("Url"),
            }
            remediation = {k: v for k, v in remediation.items() if v is not None}

    out: Dict[str, Any] = {
        "securityhub_finding": {
            "id": finding.get("Id") or trig.get("finding_arn"),
            "title": finding.get("Title"),
            "description": finding.get("Description"),
            "severity": sev_obj,
            "compliance": compliance,
            "remediation": remediation,
            "resources": finding.get("Resources"),
            "source": "SecurityHub",
            "generator_id": finding.get("GeneratorId"),
            "resource_count": len(finding.get("Resources") or []),
            "workflow_state": finding.get("WorkflowState"),
            "record_state": finding.get("RecordState"),
        }
    }
    if remediation and remediation.get("text"):
        out["securityhub_finding"]["remediation_text"] = remediation["text"]
    out["securityhub_finding"] = {k: v for k, v in out["securityhub_finding"].items() if v is not None}
    return out


def _build_aws_health_extensions(payload: Dict[str, Any], resource_refs: List[Dict[str, Any]]) -> Dict[str, Any]:
    trig = payload.get("trigger") or {}
    health = trig.get("health") or trig.get("detail") or {}
    if not isinstance(health, dict):
        return {}

    service = _service_hint_upper(health)
    event_type_code = str(health.get("eventTypeCode") or "")
    category = str(health.get("eventTypeCategory") or "")
    scope = str(health.get("eventScopeCode") or "")
    status_code = str(health.get("statusCode") or "")
    event_region = str(health.get("eventRegion") or (payload.get("regions") or [""])[0])
    affected_entities = health.get("affectedEntities") or []
    latest_description = None
    latest = health.get("latestDescription")
    if isinstance(latest, dict):
        latest_description = latest.get("text") or latest.get("latestDescription")
    elif isinstance(latest, str):
        latest_description = latest

    terraform_candidate = (
        scope == "ACCOUNT_SPECIFIC"
        and category in {"scheduledChange", "accountNotification"}
        and service in AWS_HEALTH_TERRAFORM_SERVICES
        and len(resource_refs) > 0
    )

    aws_health = {
        "event_arn": health.get("eventArn") or trig.get("event_id"),
        "service": service or None,
        "event_type_code": event_type_code or None,
        "event_type_category": category or None,
        "event_scope_code": scope or None,
        "status_code": status_code or None,
        "event_region": event_region or None,
        "affected_entity_count": len(affected_entities),
        "latest_description": latest_description,
    }
    aws_health = {k: v for k, v in aws_health.items() if v not in (None, "")}

    reason_parts = []
    if scope:
        reason_parts.append(scope)
    if category:
        reason_parts.append(category)
    if service:
        reason_parts.append(service)
    if resource_refs:
        reason_parts.append(f"resources={len(resource_refs)}")

    return {
        "aws_health": aws_health,
        "actionability": {
            "terraform_candidate": terraform_candidate,
            "reason": " / ".join(reason_parts) if reason_parts else "AWS_HEALTH",
            "auto_apply_allowed": False,
        },
    }


def build_event_source_extensions(payload: Dict[str, Any], resource_refs: List[Dict[str, Any]]) -> Dict[str, Any]:
    kind = _event_origin_kind(payload)
    ext: Dict[str, Any] = {"event_origin": {"kind": kind}}
    if kind == "SECURITYHUB":
        ext.update(_build_securityhub_extensions(payload))
    elif kind == "AWS_HEALTH":
        ext.update(_build_aws_health_extensions(payload, resource_refs))
    return ext


def _advisor_stage_ok(**extra: Any) -> Dict[str, Any]:
    d: Dict[str, Any] = {"status": "OK"}
    d.update(extra)
    return d


def _advisor_stage_na(reason: str, message: str) -> Dict[str, Any]:
    return {"status": "NA", "na_reason": reason, "message": message}


def _advisor_stage_failed(code: str, message: str) -> Dict[str, Any]:
    return {"status": "FAILED", "error_code": code, "message": message}


def _na_from_client_error(e: ClientError) -> Optional[Tuple[str, str]]:
    code = _client_error_code(e)
    if code in ("AccessDenied", "AccessDeniedException", "UnauthorizedOperation"):
        return ("PERMISSION_DENIED", f"{code}: {e}")

    msg = str(e).lower()
    if code in ("OptInRequired",):
        return ("REGION_DISABLED", f"{code}: {e}")
    if "region is not enabled" in msg or "not opted-in" in msg or "opted in" in msg:
        return ("REGION_DISABLED", f"{code}: {e}")
    if code in ("SubscriptionRequiredException",):
        return ("SERVICE_DISABLED", f"{code}: {e}")
    if "service is not enabled" in msg or "service has not been enabled" in msg or "not subscribed to this service" in msg:
        return ("SERVICE_DISABLED", f"{code}: {e}")
    return None


def _write_advisor_raw(raw_dir: Path, payload: Dict[str, Any], filename: str, obj: Any) -> str:
    advisor_dir = raw_dir / "advisor"
    _ensure_dir(advisor_dir)
    path = advisor_dir / filename
    dump_json(path, obj)
    bucket = payload["s3"]["bucket"]
    prefix = payload["s3"]["prefix"].rstrip("/")
    return _s3_uri(bucket, f"{prefix}/raw/advisor/{filename}")


def _write_access_analyzer_raw(raw_dir: Path, payload: Dict[str, Any], filename: str, obj: Any) -> str:
    aa_dir = raw_dir / "access_analyzer"
    _ensure_dir(aa_dir)
    path = aa_dir / filename
    dump_json(path, obj)
    bucket = payload["s3"]["bucket"]
    prefix = payload["s3"]["prefix"].rstrip("/")
    return _s3_uri(bucket, f"{prefix}/raw/access_analyzer/{filename}")


def _count_access_analyzer_field(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, dict):
        return len(value)
    if isinstance(value, (list, tuple, set)):
        return len(value)
    return 1


def _resource_ref(resource_type: str, resource_id: str, region: Optional[str], account_id: str, arn: Optional[str] = None) -> Dict[str, Any]:
    ref: Dict[str, Any] = {
        "resource_type": resource_type,
        "resource_id": resource_id,
        "account_id": account_id,
    }
    if region:
        ref["region"] = region
    if arn:
        ref["arn"] = arn
    return ref


def build_weekly_advisor_extensions(
    session: boto3.Session,
    payload: Dict[str, Any],
    raw_dir: Path,
) -> Dict[str, Any]:
    if payload.get("type") != "WEEKLY":
        return {}

    account_id = payload.get("account_id", "")
    regions = payload.get("regions") or []
    checks: List[Dict[str, Any]] = []
    collection: Dict[str, Any] = {}

    for region in regions:
        # EC2: Elastic IPs
        try:
            ec2 = session.client("ec2", region_name=region)
            addresses = ec2.describe_addresses()
            uri = _write_advisor_raw(raw_dir, payload, f"ec2_describe_addresses_{region}.json", addresses)
            collection[f"ec2.describe_addresses.{region}"] = _advisor_stage_ok(raw_s3_uri=uri, count=len(addresses.get("Addresses", []) or []))

            for a in addresses.get("Addresses", []) or []:
                associated = bool(a.get("AssociationId") or a.get("NetworkInterfaceId") or a.get("InstanceId"))
                if associated:
                    continue
                alloc_id = a.get("AllocationId") or a.get("PublicIp") or "unknown-eip"
                checks.append({
                    "check_id": f"UNUSED_EIP::{region}::{alloc_id}",
                    "category": "COST_OPTIMIZATION",
                    "severity": "MEDIUM",
                    "title": "미사용 Elastic IP",
                    "summary": "할당은 되어 있으나 어떤 리소스와도 연결되지 않은 EIP입니다.",
                    "resources": [
                        _resource_ref("AWS::EC2::EIP", alloc_id, region, account_id)
                    ],
                    "recommendation": "사용하지 않으면 release 하거나 필요한 리소스에 연결하세요.",
                    "evidence": {"raw_s3_uri": uri},
                })
        except ClientError as e:
            na = _na_from_client_error(e)
            if na is not None:
                na_reason, message = na
                collection[f"ec2.describe_addresses.{region}"] = _advisor_stage_na(na_reason, message)
            else:
                code = _client_error_code(e)
                collection[f"ec2.describe_addresses.{region}"] = _advisor_stage_failed("EC2_DESCRIBE_ADDRESSES_FAILED", f"{code}: {e}")
        except Exception as e:
            collection[f"ec2.describe_addresses.{region}"] = _advisor_stage_failed("EC2_DESCRIBE_ADDRESSES_UNEXPECTED", str(e))

        # EBS: unattached volumes
        try:
            ec2 = session.client("ec2", region_name=region)
            paginator = ec2.get_paginator("describe_volumes")
            pages = list(paginator.paginate(Filters=[{"Name": "status", "Values": ["available"]}]))
            volumes_resp = {"Volumes": [v for pg in pages for v in pg.get("Volumes", [])]}
            uri = _write_advisor_raw(raw_dir, payload, f"ec2_describe_available_volumes_{region}.json", volumes_resp)
            collection[f"ec2.describe_volumes.{region}"] = _advisor_stage_ok(raw_s3_uri=uri, count=len(volumes_resp["Volumes"]))

            for v in volumes_resp["Volumes"]:
                vol_id = v.get("VolumeId") or "unknown-volume"
                checks.append({
                    "check_id": f"UNATTACHED_EBS::{region}::{vol_id}",
                    "category": "COST_OPTIMIZATION",
                    "severity": "MEDIUM",
                    "title": "미연결 EBS 볼륨",
                    "summary": "어떤 EC2 인스턴스에도 연결되지 않은 EBS 볼륨입니다.",
                    "resources": [
                        _resource_ref("AWS::EC2::Volume", vol_id, region, account_id)
                    ],
                    "recommendation": "사용하지 않으면 삭제하거나 필요한 인스턴스에 연결하세요.",
                    "evidence": {"raw_s3_uri": uri},
                })
        except ClientError as e:
            na = _na_from_client_error(e)
            if na is not None:
                na_reason, message = na
                collection[f"ec2.describe_volumes.{region}"] = _advisor_stage_na(na_reason, message)
            else:
                code = _client_error_code(e)
                collection[f"ec2.describe_volumes.{region}"] = _advisor_stage_failed("EC2_DESCRIBE_VOLUMES_FAILED", f"{code}: {e}")
        except Exception as e:
            collection[f"ec2.describe_volumes.{region}"] = _advisor_stage_failed("EC2_DESCRIBE_VOLUMES_UNEXPECTED", str(e))

        # RDS: backup / MultiAZ
        try:
            rds = session.client("rds", region_name=region)
            paginator = rds.get_paginator("describe_db_instances")
            pages = list(paginator.paginate())
            dbs_resp = {"DBInstances": [db for pg in pages for db in pg.get("DBInstances", [])]}
            uri = _write_advisor_raw(raw_dir, payload, f"rds_describe_db_instances_{region}.json", dbs_resp)
            collection[f"rds.describe_db_instances.{region}"] = _advisor_stage_ok(raw_s3_uri=uri, count=len(dbs_resp["DBInstances"]))

            for db in dbs_resp["DBInstances"]:
                db_id = db.get("DBInstanceIdentifier") or "unknown-db"
                db_arn = db.get("DBInstanceArn")
                if int(db.get("BackupRetentionPeriod", 0) or 0) == 0:
                    checks.append({
                        "check_id": f"RDS_BACKUP_DISABLED::{region}::{db_id}",
                        "category": "FAULT_TOLERANCE",
                        "severity": "HIGH",
                        "title": "RDS 백업 비활성화",
                        "summary": "DB 인스턴스의 백업 보존 기간이 0으로 설정되어 있습니다.",
                        "resources": [
                            _resource_ref("AWS::RDS::DBInstance", db_id, region, account_id, arn=db_arn)
                        ],
                        "recommendation": "BackupRetentionPeriod를 1일 이상으로 설정하세요.",
                        "evidence": {"raw_s3_uri": uri},
                    })
                if not bool(db.get("MultiAZ")):
                    checks.append({
                        "check_id": f"RDS_SINGLE_AZ::{region}::{db_id}",
                        "category": "FAULT_TOLERANCE",
                        "severity": "MEDIUM",
                        "title": "RDS Multi-AZ 미설정",
                        "summary": "DB 인스턴스가 단일 AZ로 구성되어 있습니다.",
                        "resources": [
                            _resource_ref("AWS::RDS::DBInstance", db_id, region, account_id, arn=db_arn)
                        ],
                        "recommendation": "운영 환경이면 Multi-AZ 구성을 검토하세요.",
                        "evidence": {"raw_s3_uri": uri},
                    })
        except ClientError as e:
            na = _na_from_client_error(e)
            if na is not None:
                na_reason, message = na
                collection[f"rds.describe_db_instances.{region}"] = _advisor_stage_na(na_reason, message)
            else:
                code = _client_error_code(e)
                collection[f"rds.describe_db_instances.{region}"] = _advisor_stage_failed("RDS_DESCRIBE_DB_INSTANCES_FAILED", f"{code}: {e}")
        except Exception as e:
            collection[f"rds.describe_db_instances.{region}"] = _advisor_stage_failed("RDS_DESCRIBE_DB_INSTANCES_UNEXPECTED", str(e))

    severity_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    checks.sort(key=lambda c: (severity_order.get(c.get("severity", "LOW"), 9), c.get("category", ""), c.get("check_id", "")))

    sev_counts: Dict[str, int] = {}
    cat_counts: Dict[str, int] = {}
    for c in checks:
        sev = c.get("severity", "UNKNOWN")
        cat = c.get("category", "UNKNOWN")
        sev_counts[sev] = sev_counts.get(sev, 0) + 1
        cat_counts[cat] = cat_counts.get(cat, 0) + 1

    return {
        "advisor_collection_status": collection,
        "advisor_checks": checks,
        "advisor_rollup": {
            "total_checks": len(checks),
            "severity_counts": sev_counts,
            "category_counts": cat_counts,
        },
    }


def _serialize_access_analyzer_finding(finding: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": finding.get("id"),
        "status": finding.get("status"),
        "resource_type": finding.get("resourceType"),
        "resource": finding.get("resource"),
        "resource_owner_account": finding.get("resourceOwnerAccount"),
        "is_public": finding.get("isPublic"),
        "principal_count": _count_access_analyzer_field(finding.get("principal")),
        "action_count": _count_access_analyzer_field(finding.get("action")),
        "source_count": _count_access_analyzer_field(finding.get("sources")),
        "created_at": _to_kst_iso(finding["createdAt"]) if isinstance(finding.get("createdAt"), datetime) else None,
        "updated_at": _to_kst_iso(finding["updatedAt"]) if isinstance(finding.get("updatedAt"), datetime) else None,
        "error": finding.get("error"),
    }


def build_weekly_access_analyzer_extensions(
    session: boto3.Session,
    payload: Dict[str, Any],
    raw_dir: Path,
    *,
    max_findings_per_analyzer: int = 100,
) -> Dict[str, Any]:
    if payload.get("type") != "WEEKLY":
        return {}

    findings: List[Dict[str, Any]] = []
    collection: Dict[str, Any] = {}
    total_analyzers = 0

    for region in payload.get("regions") or []:
        try:
            client = session.client("accessanalyzer", region_name=region)
            analyzers: List[Dict[str, Any]] = []
            token = None
            while True:
                kwargs: Dict[str, Any] = {"maxResults": 100}
                if token:
                    kwargs["nextToken"] = token
                resp = client.list_analyzers(**kwargs)
                analyzers.extend(resp.get("analyzers", []) or [])
                token = resp.get("nextToken")
                if not token:
                    break

            raw_uri = _write_access_analyzer_raw(
                raw_dir,
                payload,
                f"list_analyzers_{region}.json",
                {"analyzers": analyzers},
            )
            active_analyzers = [
                analyzer
                for analyzer in analyzers
                if str(analyzer.get("status") or "").upper() == "ACTIVE"
            ]
            total_analyzers += len(active_analyzers)
            collection[f"access_analyzer.list_analyzers.{region}"] = _advisor_stage_ok(
                raw_s3_uri=raw_uri,
                analyzer_count=len(active_analyzers),
            )

            for analyzer in active_analyzers:
                analyzer_name = analyzer.get("name") or "unknown-analyzer"
                analyzer_arn = analyzer.get("arn")
                if not analyzer_arn:
                    continue

                region_findings: List[Dict[str, Any]] = []
                token = None
                while len(region_findings) < max_findings_per_analyzer:
                    kwargs = {
                        "analyzerArn": analyzer_arn,
                        "maxResults": min(100, max_findings_per_analyzer - len(region_findings)),
                    }
                    if token:
                        kwargs["nextToken"] = token
                    resp = client.list_findings(**kwargs)
                    region_findings.extend(resp.get("findings", []) or [])
                    token = resp.get("nextToken")
                    if not token:
                        break

                findings_uri = _write_access_analyzer_raw(
                    raw_dir,
                    payload,
                    f"list_findings_{region}_{_safe_fs_name(analyzer_name)}.json",
                    {
                        "analyzer": {
                            "arn": analyzer_arn,
                            "name": analyzer_name,
                            "type": analyzer.get("type"),
                            "status": analyzer.get("status"),
                        },
                        "findings": region_findings,
                    },
                )
                collection[f"access_analyzer.list_findings.{region}.{analyzer_name}"] = _advisor_stage_ok(
                    raw_s3_uri=findings_uri,
                    finding_count=len(region_findings),
                )

                for finding in region_findings:
                    item = _serialize_access_analyzer_finding(finding)
                    item["region"] = region
                    item["analyzer_name"] = analyzer_name
                    item["analyzer_type"] = analyzer.get("type")
                    item["evidence"] = {"raw_s3_uri": findings_uri}
                    findings.append({k: v for k, v in item.items() if v is not None})

        except ClientError as e:
            na = _na_from_client_error(e)
            if na is not None:
                na_reason, message = na
                collection[f"access_analyzer.list_analyzers.{region}"] = _advisor_stage_na(na_reason, message)
            else:
                code = _client_error_code(e)
                collection[f"access_analyzer.list_analyzers.{region}"] = _advisor_stage_failed(
                    "ACCESS_ANALYZER_LIST_ANALYZERS_FAILED",
                    f"{code}: {e}",
                )
        except Exception as e:
            collection[f"access_analyzer.list_analyzers.{region}"] = _advisor_stage_failed(
                "ACCESS_ANALYZER_UNEXPECTED",
                str(e),
            )

    findings.sort(
        key=lambda f: (
            0 if f.get("is_public") else 1,
            str(f.get("resource_type", "")),
            str(f.get("id", "")),
        )
    )

    resource_type_counts: Dict[str, int] = {}
    public_count = 0
    for finding in findings:
        r_type = str(finding.get("resource_type") or "UNKNOWN")
        resource_type_counts[r_type] = resource_type_counts.get(r_type, 0) + 1
        if finding.get("is_public") is True:
            public_count += 1

    return {
        "access_analyzer_collection_status": collection,
        "access_analyzer_findings": findings,
        "access_analyzer_rollup": {
            "analyzer_count": total_analyzers,
            "finding_count": len(findings),
            "public_finding_count": public_count,
            "resource_type_counts": resource_type_counts,
        },
    }


def _extract_user_identity(ct_detail: Dict[str, Any]) -> Dict[str, Any]:
    ui = ct_detail.get("userIdentity") or {}
    out: Dict[str, Any] = {}
    if isinstance(ui, dict):
        if "type" in ui:
            out["type"] = ui.get("type")
        if "arn" in ui:
            out["arn"] = ui.get("arn")
        if "principalId" in ui:
            out["principal_id"] = ui.get("principalId")
        if "accountId" in ui:
            out["account_id"] = ui.get("accountId")
        if "userName" in ui:
            out["user_name"] = ui.get("userName")
    return out


def _normalize_resources(
    raw_event: Dict[str, Any],
    account_id: str,
) -> List[Dict[str, Any]]:
    region = raw_event.get("AwsRegion") or ""
    out: List[Dict[str, Any]] = []
    for r in raw_event.get("Resources", []) or []:
        r_type = r.get("ResourceType") or "UNKNOWN"
        r_id = r.get("ResourceName") or ""
        if not r_id:
            continue
        ref: Dict[str, Any] = {
            "resource_type": r_type,
            "resource_id": r_id,
            "account_id": account_id,
        }
        if region:
            ref["region"] = region
        # If ResourceName looks like ARN, keep it also as arn
        if isinstance(r_id, str) and r_id.startswith("arn:"):
            ref["arn"] = r_id
        out.append(ref)
    return out


def normalize_cloudtrail_events(
    raw_events: List[Dict[str, Any]],
    payload: Dict[str, Any],
    raw_s3_uris: Dict[str, Any],
) -> List[Dict[str, Any]]:
    account_id = payload["account_id"]
    job_type = payload["type"]

    normalized: List[Dict[str, Any]] = []
    for e in raw_events:
        # CloudTrail lookup_events returns CloudTrailEvent as JSON string
        ct_detail: Dict[str, Any] = {}
        try:
            if isinstance(e.get("CloudTrailEvent"), str):
                ct_detail = json.loads(e["CloudTrailEvent"])
        except Exception:
            ct_detail = {}

        read_only = bool(ct_detail.get("readOnly", False))
        # Prefer WRITE events, but keep readOnly in case (schema allows)
        # If you want strict WRITE-only output, uncomment:
        # if read_only: continue

        event_time = e.get("EventTime")
        if isinstance(event_time, datetime):
            event_time_iso = _to_kst_iso(event_time)
        else:
            # fallback
            event_time_iso = _to_kst_iso(_now_kst())

        # Raw pointers
        raw_ptr: Dict[str, Any] = {}
        if job_type == "WEEKLY":
            raw_ptr["lookup_event_s3_uri"] = raw_s3_uris["weekly_lookup_jsonl"]
        else:
            # EVENT: per-event file
            event_map = raw_s3_uris.get("event_file_uri_by_id") or {}
            if not isinstance(event_map, dict):
                event_map = {}
            default_uri = raw_s3_uris.get("event_default_json")
            raw_ptr["cloudtrail_event_s3_uri"] = event_map.get(e.get("EventId", ""), default_uri)
        # Optional sha256 is omitted in MVP

        resources = _normalize_resources(e, account_id=account_id)
        # If event payload has an explicit hint.resource, ensure at least one resource exists
        hint_res = (payload.get("hint") or {}).get("resource")
        if isinstance(hint_res, dict) and hint_res.get("resource_type") and hint_res.get("resource_id"):
            hint_ref = {
                "resource_type": hint_res["resource_type"],
                "resource_id": hint_res["resource_id"],
                "account_id": account_id,
                "region": hint_res.get("region") or e.get("AwsRegion"),
            }
            if hint_ref not in resources:
                resources.append(hint_ref)

        norm = {
            "event_id": e.get("EventId") or hashlib.md5((e.get("EventName","") + event_time_iso).encode()).hexdigest(),
            "event_time": event_time_iso,
            "aws_region": e.get("AwsRegion") or payload["regions"][0],
            "event_source": e.get("EventSource") or "",
            "event_name": e.get("EventName") or "",
            "read_only": read_only,
            "resources": resources,
            "raw": raw_ptr,
        }

        user_identity = _extract_user_identity(ct_detail)
        if user_identity:
            norm["user_identity"] = user_identity

        normalized.append(norm)

    # Deterministic sort: time then id
    normalized.sort(key=lambda x: (x.get("event_time", ""), x.get("event_id", "")))
    return normalized


def group_resources(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Build resources[] (resource_group) from events[].
    Group key: "<region>:<resource_type>:<resource_id>"
    """
    groups: Dict[str, Dict[str, Any]] = {}

    for ev in events:
        for r in ev.get("resources", []) or []:
            region = r.get("region") or ev.get("aws_region") or ""
            key = f"{region}:{r['resource_type']}:{r['resource_id']}"
            g = groups.get(key)
            if g is None:
                # resource_group
                resource_ref = {
                    "resource_type": r["resource_type"],
                    "resource_id": r["resource_id"],
                }
                # Optional fields
                if r.get("arn"):
                    resource_ref["arn"] = r["arn"]
                if r.get("account_id"):
                    resource_ref["account_id"] = r["account_id"]
                if region:
                    resource_ref["region"] = region

                g = {
                    "key": key,
                    "resource": resource_ref,
                    "events": [],
                }
                groups[key] = g

            link = {
                "event_id": ev["event_id"],
                "event_time": ev.get("event_time"),
                "event_name": ev.get("event_name"),
                "event_source": ev.get("event_source"),
            }
            user_arn = (ev.get("user_identity") or {}).get("arn")
            if isinstance(user_arn, str) and user_arn.strip():
                link["user_arn"] = user_arn
            g["events"].append(link)

    # Deduplicate + sort event links for determinism
    for g in groups.values():
        uniq = {}
        for el in g["events"]:
            uniq[el["event_id"]] = el
        g["events"] = list(uniq.values())
        g["events"].sort(key=lambda x: (x.get("event_time", ""), x.get("event_id", "")))

        # Optional change_summary
        if g["events"]:
            first = g["events"][0]["event_time"]
            last = g["events"][-1]["event_time"]
            g["change_summary"] = {
                "event_count": len(g["events"]),
                "first_event_time": first,
                "last_event_time": last,
            }

    # Deterministic sort of resource groups by key
    out = list(groups.values())
    out.sort(key=lambda x: x["key"])
    return out


def build_meta(payload: Dict[str, Any], time_range: Dict[str, Any]) -> Dict[str, Any]:
    run_id = payload.get("run_id") or ("run-" + _sha256_bytes(os.urandom(16))[:12])
    evidence = _evidence_uris(payload)
    meta = {
        "schema_version": "0.2.0",
        "type": payload["type"],
        "run_id": run_id,
        "account_id": payload["account_id"],
        "regions": payload["regions"],
        "time_range": time_range,
        "generated_at": _to_kst_iso(_now_kst()),
        "collector": {
            "name": "dndn-collector",
            "version": "0.1.0",
            "runtime": f"python{sys.version_info.major}.{sys.version_info.minor}",
            "rule_set_version": payload.get("rule_set_version", "unknown"),
        },
        "evidence": evidence,
        "partition": build_partition(payload, time_range),
    }

    # EVENT requires trigger
    if payload["type"] == "EVENT":
        trig_in = payload.get("trigger") or {}
        # Minimal trigger fields required by schema: source, received_at
        health = trig_in.get("health") or trig_in.get("detail") or {}
        trigger_event_id = (
            trig_in.get("event_id")
            or trig_in.get("finding_arn")
            or (health.get("eventArn") if isinstance(health, dict) else None)
        )
        detail_type = trig_in.get("detail_type")
        if not detail_type and "finding_arn" in trig_in:
            detail_type = "Security Hub Findings - Imported"
        if not detail_type and isinstance(health, dict) and health.get("eventTypeCode"):
            detail_type = "AWS Health Event"
        meta["trigger"] = {
            "source": _transport_source_for_meta(trig_in.get("source", "EVENTBRIDGE")),
            "received_at": _to_kst_iso(_now_kst()),
            "event_id": trigger_event_id,
            "event_time": payload.get("event_time"),
            "detail_type": detail_type,
            "raw_event_s3_uri": trig_in.get("raw_event_s3_uri"),
            "selector": trig_in.get("selector"),
        }
        # Remove None keys for cleanliness
        meta["trigger"] = {k: v for k, v in meta["trigger"].items() if v is not None}

    return meta


def _contract_paths(repo_root: Path) -> Tuple[Path, Path, Path]:
    contracts_dir = repo_root / "contracts"
    payload_schema = contracts_dir / "payload" / "job_payload.schema.json"
    canonical_schema = contracts_dir / "canonical_model.schema.json"
    event_schema = contracts_dir / "event_model.schema.json"
    return payload_schema, canonical_schema, event_schema


def _result_path_for_job(job_dir: Path, job_type: str) -> Path:
    return job_dir / "normalized" / ("event.json" if job_type == "EVENT" else "canonical.json")


def run_job_from_payload(
    payload: Dict[str, Any],
    repo_root: Path,
    out_root: Path,
    max_cloudtrail_events: int = 500,
) -> WorkerExecutionResult:
    """
    End-to-end runner:
      payload dict -> raw/ -> normalized/{canonical|event}.json
    Returns path to normalized json file.
    """
    payload_schema, canonical_schema, event_schema = _contract_paths(repo_root)

    payload = dict(payload)
    try:
        validate_with_schema(payload, payload_schema)
    except ValueError as exc:
        raise WorkerExecutionError(
            "INVALID_PAYLOAD",
            str(exc),
            retryable=False,
        ) from exc

    run_id = payload.get("run_id") or ("run-" + _sha256_bytes(os.urandom(16))[:12])
    payload["run_id"] = run_id
    job_type = payload["type"]

    # Local output structure (independent of S3)
    job_dir = out_root / run_id
    raw_dir = job_dir / "raw"
    norm_dir = job_dir / "normalized"
    result_path = _result_path_for_job(job_dir, job_type)
    if result_path.exists():
        return WorkerExecutionResult(
            run_id=run_id,
            result_path=result_path,
            job_type=job_type,
            already_processed=True,
        )

    _ensure_dir(raw_dir / "meta")
    _ensure_dir(norm_dir)

    # Store payload as raw evidence (local)
    dump_json(raw_dir / "meta" / "job_payload.json", payload)

    trigger_artifact_s3_uri = _write_trigger_artifact(raw_dir, payload)
    if trigger_artifact_s3_uri:
        payload.setdefault("trigger", {})
        if isinstance(payload["trigger"], dict):
            payload["trigger"]["raw_event_s3_uri"] = trigger_artifact_s3_uri

    # 저장은 항상 "우리(DnDn) 계정" 권한으로 수행
    storage_session = boto3.Session()

    def _upload_all_artifacts() -> None:
        bucket = payload["s3"]["bucket"]
        prefix = payload["s3"]["prefix"].rstrip("/")
        upload_tree_to_s3(
            session=storage_session,
            local_root=job_dir,
            bucket=bucket,
            prefix=prefix,
        )

    def _upload_result_json_only(result_path: Path) -> None:
        bucket = payload["s3"]["bucket"]
        prefix = payload["s3"]["prefix"].rstrip("/")
        key = f"{prefix}/normalized/{result_path.name}".lstrip("/")
        storage_session.client("s3").upload_file(
            str(result_path),
            bucket,
            key,
            ExtraArgs={
                "ServerSideEncryption": "AES256",
                "ContentType": "application/json",
            },
        )

    def _finalize_result(result_path: Path, result_obj: Dict[str, Any], strict_upload: bool) -> Path:
        bucket = payload["s3"]["bucket"]
        prefix = payload["s3"]["prefix"].rstrip("/")

        result_obj.setdefault("extensions", {})
        dump_json(result_path, result_obj)
        _write_artifact_index(job_dir, payload)

        upload_status: Dict[str, Any] = {"ok": True, "bucket": bucket, "prefix": prefix}
        try:
            _upload_all_artifacts()
        except Exception as upload_err:
            upload_status = {
                "ok": False,
                "bucket": bucket,
                "prefix": prefix,
                "error": str(upload_err),
            }
            result_obj["extensions"]["upload"] = upload_status
            dump_json(result_path, result_obj)
            if strict_upload:
                raise WorkerExecutionError(
                    "S3_PUT_FAILED",
                    f"S3 업로드 실패: {upload_err}",
                    retryable=True,
                ) from upload_err
            return result_path

        result_obj["extensions"]["upload"] = upload_status
        dump_json(result_path, result_obj)

        try:
            _upload_result_json_only(result_path)
        except Exception as sync_err:
            result_obj["extensions"]["upload_sync_warning"] = str(sync_err)
            dump_json(result_path, result_obj)
            if strict_upload:
                raise WorkerExecutionError(
                    "S3_PUT_FAILED",
                    f"최종 normalized 결과 동기화 실패: {sync_err}",
                    retryable=True,
                ) from sync_err

        return result_path

    collection_status: Dict[str, Any] = {
        "assume_role": {"status": "NA", "na_reason": "UNKNOWN", "message": "not started"},
        "cloudtrail": {"status": "NA", "na_reason": "UNKNOWN", "message": "not started"},
        "config": {"status": "NA", "na_reason": "UNKNOWN", "message": "not started"},
        "normalized": {"status": "NA", "na_reason": "UNKNOWN", "message": "not started"},
    }

    # 1) AssumeRole
    try:
        role_arn = payload["assume_role"]["role_arn"]
        ext_id = payload["assume_role"]["external_id"]
        session = assume_role_session(
            role_arn=role_arn,
            external_id=ext_id,
            run_id=run_id,
            base_session=storage_session,
        )
        collection_status["assume_role"] = _stage_ok()
    except (ClientError, BotoCoreError) as e:
        code = _client_error_code(e) if isinstance(e, ClientError) else e.__class__.__name__
        collection_status["assume_role"] = _stage_failed(
            "ASSUME_ROLE_FAILED",
            f"{code}: {e}",
            retryable=False,
        )
        failed_result = {
            "meta": build_meta(payload, resolve_time_range(payload)),
            "collection_status": collection_status,
            "events": [],
            "resources": [],
            "extensions": {
                "fatal": True,
                "note": "assume_role failed; no further collection",
            },
        }
        finalized_path = _finalize_result(result_path, failed_result, strict_upload=False)
        return WorkerExecutionResult(
            run_id=run_id,
            result_path=finalized_path,
            job_type=job_type,
            retryable=False,
            error_code="ASSUME_ROLE_FAILED",
        )

    # 2) Resolve time range
    time_range = resolve_time_range(payload)
    start_dt = _parse_dt(time_range["start"])
    end_dt = _parse_dt(time_range["end"])
    if start_dt.tzinfo is None:
        start_dt = start_dt.replace(tzinfo=timezone.utc)
    if end_dt.tzinfo is None:
        end_dt = end_dt.replace(tzinfo=timezone.utc)

    # 3) CloudTrail collect
    raw_events: List[Dict[str, Any]] = []
    raw_s3_uris: Dict[str, Any] = {}
    try:
        raw_events = collect_cloudtrail_lookup_events(
            session=session,
            regions=payload["regions"],
            start=start_dt.astimezone(timezone.utc),
            end=end_dt.astimezone(timezone.utc),
            max_events=max_cloudtrail_events,
        )
        collection_status["cloudtrail"] = _stage_ok()
    except (ClientError, BotoCoreError) as e:
        if isinstance(e, ClientError):
            code = _client_error_code(e)
            # Treat access issues as NA(PERMISSION_DENIED) (typical for customer accounts)
            if code in ("AccessDenied", "AccessDeniedException", "UnauthorizedOperation"):
                collection_status["cloudtrail"] = _stage_na("PERMISSION_DENIED", f"{code}: {e}")
            else:
                collection_status["cloudtrail"] = _stage_failed("CLOUDTRAIL_LOOKUP_FAILED", f"{code}: {e}", retryable=True)
        else:
            collection_status["cloudtrail"] = _stage_failed(
                "CLOUDTRAIL_LOOKUP_FAILED",
                f"{e.__class__.__name__}: {e}",
                retryable=True,
            )

    # 3-1) Store raw CloudTrail (local)
    _ensure_dir(raw_dir / "cloudtrail")
    if job_type == "WEEKLY":
        lookup_path = raw_dir / "cloudtrail" / "lookup_events.jsonl"
        dump_jsonl(lookup_path, raw_events)
        raw_s3_uris["weekly_lookup_jsonl"] = _s3_uri(payload["s3"]["bucket"], f"{payload['s3']['prefix'].rstrip('/')}/raw/cloudtrail/lookup_events.jsonl")
        raw_s3_uris["event_default_json"] = None
        raw_s3_uris["event_file_uri_by_id"] = {}
    else:
        event_file_uri_by_id: Dict[str, str] = {}
        for e in raw_events:
            eid = e.get("EventId") or "unknown"
            p = raw_dir / "cloudtrail" / f"event_{eid}.json"
            dump_json(p, e)
            event_file_uri_by_id[eid] = _s3_uri(payload["s3"]["bucket"], f"{payload['s3']['prefix'].rstrip('/')}/raw/cloudtrail/event_{eid}.json")
        raw_s3_uris["weekly_lookup_jsonl"] = None
        raw_s3_uris["event_default_json"] = _s3_uri(payload["s3"]["bucket"], f"{payload['s3']['prefix'].rstrip('/')}/raw/cloudtrail/")
        raw_s3_uris["event_file_uri_by_id"] = event_file_uri_by_id

    # 4) Config enabled check (best effort)
    try:
        enabled, msg = detect_config_enabled(session, payload["regions"][0])
        if enabled:
            collection_status["config"] = _stage_ok()
        else:
            collection_status["config"] = _stage_na("SERVICE_DISABLED", msg)
    except (ClientError, BotoCoreError) as e:
        if isinstance(e, ClientError):
            code = _client_error_code(e)
            if code in ("AccessDenied", "AccessDeniedException", "UnauthorizedOperation"):
                collection_status["config"] = _stage_na("PERMISSION_DENIED", f"{code}: {e}")
            else:
                collection_status["config"] = _stage_failed("CONFIG_DESCRIBE_FAILED", f"{code}: {e}", retryable=True)
        else:
            collection_status["config"] = _stage_failed(
                "CONFIG_DESCRIBE_FAILED",
                f"{e.__class__.__name__}: {e}",
                retryable=True,
            )

    # 5) Normalize
    events = normalize_cloudtrail_events(raw_events, payload, raw_s3_uris)
    resources = group_resources(events)

    trigger_resource_refs = _extract_trigger_resource_refs(payload)
    resources = merge_resource_groups_with_trigger_refs(resources, trigger_resource_refs)

    enrich_resources_with_config(
        session=session,
        resources=resources,
        payload=payload,
        raw_dir=raw_dir,
        collection_status=collection_status,
    )

    extensions = build_event_source_extensions(payload, trigger_resource_refs)
    extensions.update(build_weekly_advisor_extensions(session, payload, raw_dir))
    extensions.update(build_weekly_access_analyzer_extensions(session, payload, raw_dir))

    result = {
        "meta": build_meta(payload, time_range),
        "collection_status": collection_status,
        "events": events,
        "resources": resources,
        "extensions": extensions,
    }

    # 6) Schema validate + save
    try:
        if job_type == "EVENT":
            validate_with_schema(result, event_schema)
        else:
            validate_with_schema(result, canonical_schema)
        collection_status["normalized"] = _stage_ok()
    except Exception as e:
        collection_status["normalized"] = _stage_failed("SCHEMA_VALIDATION_FAILED", str(e), retryable=False)
        result["extensions"]["schema_error"] = str(e)

    finalized_path = _finalize_result(result_path, result, strict_upload=True)
    normalized_status = collection_status["normalized"]
    return WorkerExecutionResult(
        run_id=run_id,
        result_path=finalized_path,
        job_type=job_type,
        retryable=bool(normalized_status.get("retryable", False)),
        error_code=normalized_status.get("error_code"),
    )


def run_job_from_payload_file(
    payload_path: Path,
    repo_root: Path,
    out_root: Path,
    max_cloudtrail_events: int = 500,
) -> WorkerExecutionResult:
    """
    Thin file wrapper for local/CLI execution.
    """
    payload = load_json(payload_path)
    return run_job_from_payload(
        payload=payload,
        repo_root=repo_root,
        out_root=out_root,
        max_cloudtrail_events=max_cloudtrail_events,
    )
