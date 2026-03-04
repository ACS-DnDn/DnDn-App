\
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
from botocore.exceptions import ClientError
from jsonschema import Draft202012Validator

try:
    # Python 3.9+
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None  # type: ignore


KST_TZ = "Asia/Seoul"


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


def assume_role_session(role_arn: str, external_id: str) -> boto3.Session:
    """
    Production path: use STS AssumeRole.
    Dev shortcut: if role_arn == 'SELF', return default session.
    """
    if role_arn.strip().upper() == "SELF":
        return boto3.Session()

    sts = boto3.client("sts")
    resp = sts.assume_role(
        RoleArn=role_arn,
        RoleSessionName="dndn-collector",
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
    return {
        "raw_prefix_s3_uri": raw_prefix,
        "normalized_prefix_s3_uri": norm_prefix,
        "job_payload_s3_uri": job_payload_uri,
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
            raw_ptr["cloudtrail_event_s3_uri"] = raw_s3_uris["event_file_uri_by_id"].get(e.get("EventId", ""), raw_s3_uris["event_default_json"])
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

            g["events"].append({
                "event_id": ev["event_id"],
                "event_time": ev.get("event_time"),
                "event_name": ev.get("event_name"),
                "event_source": ev.get("event_source"),
                "user_arn": (ev.get("user_identity") or {}).get("arn"),
            })

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
        meta["trigger"] = {
            "source": str(trig_in.get("source", "EVENTBRIDGE")),
            "received_at": _to_kst_iso(_now_kst()),
            "event_id": trig_in.get("event_id") or trig_in.get("finding_arn"),
            "event_time": payload.get("event_time"),
            "detail_type": trig_in.get("detail_type") or ("Security Hub Findings - Imported" if "finding_arn" in trig_in else None),
            "raw_event_s3_uri": trig_in.get("raw_event_s3_uri"),
            "selector": trig_in.get("selector"),
        }
        # Remove None keys for cleanliness
        meta["trigger"] = {k: v for k, v in meta["trigger"].items() if v is not None}

    return meta


def run_job_from_payload_file(
    payload_path: Path,
    repo_root: Path,
    out_root: Path,
    max_cloudtrail_events: int = 500,
) -> Path:
    """
    End-to-end runner:
      payload.json -> raw/ -> normalized/{canonical|event}.json
    Returns path to normalized json file.
    """
    contracts_dir = repo_root / "contracts"
    payload_schema = contracts_dir / "payload" / "job_payload.schema.json"
    canonical_schema = contracts_dir / "canonical_model.schema.json"
    event_schema = contracts_dir / "event_model.schema.json"

    payload = load_json(payload_path)
    validate_with_schema(payload, payload_schema)

    run_id = payload.get("run_id") or ("run-" + _sha256_bytes(os.urandom(16))[:12])
    job_type = payload["type"]

    # Local output structure (independent of S3)
    job_dir = out_root / run_id
    raw_dir = job_dir / "raw"
    norm_dir = job_dir / "normalized"
    _ensure_dir(raw_dir / "meta")
    _ensure_dir(norm_dir)

    # Store payload as raw evidence (local)
    dump_json(raw_dir / "meta" / "job_payload.json", payload)

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
        session = assume_role_session(role_arn, ext_id)
        collection_status["assume_role"] = _stage_ok()
    except ClientError as e:
        collection_status["assume_role"] = _stage_failed(
            "ASSUME_ROLE_FAILED",
            f"{_client_error_code(e)}: {e}",
            retryable=False,
        )
        # Can't proceed
        result_path = norm_dir / ("event.json" if job_type == "EVENT" else "canonical.json")
        dump_json(result_path, {
            "meta": {"schema_version": "0.2.0", "type": job_type, "run_id": run_id, "account_id": payload["account_id"], "regions": payload["regions"],
                     "time_range": resolve_time_range(payload), "generated_at": _to_kst_iso(_now_kst()),
                     "collector": {"name":"dndn-collector","version":"0.1.0"},
                     "evidence": _evidence_uris(payload)},
            "collection_status": collection_status,
            "events": [],
            "resources": [],
            "extensions": {"fatal": True, "note": "assume_role failed; no further collection"},
        })
        return result_path

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
    except ClientError as e:
        code = _client_error_code(e)
        # Treat access issues as NA(PERMISSION_DENIED) (typical for customer accounts)
        if code in ("AccessDenied", "AccessDeniedException", "UnauthorizedOperation"):
            collection_status["cloudtrail"] = _stage_na("PERMISSION_DENIED", f"{code}: {e}")
        else:
            collection_status["cloudtrail"] = _stage_failed("CLOUDTRAIL_LOOKUP_FAILED", f"{code}: {e}", retryable=True)

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
    except ClientError as e:
        code = _client_error_code(e)
        if code in ("AccessDenied", "AccessDeniedException", "UnauthorizedOperation"):
            collection_status["config"] = _stage_na("PERMISSION_DENIED", f"{code}: {e}")
        else:
            collection_status["config"] = _stage_failed("CONFIG_DESCRIBE_FAILED", f"{code}: {e}", retryable=True)

    # 5) Normalize
    events = normalize_cloudtrail_events(raw_events, payload, raw_s3_uris)
    resources = group_resources(events)

    # If Config stage is NA, optionally propagate to each resource group (consistent UX for B)
    if collection_status["config"]["status"] == "NA":
        for g in resources:
            g["config"] = {
                "status": "NA",
                "na_reason": collection_status["config"]["na_reason"],
                "message": "Config not recording",
            }

    result = {
        "meta": build_meta(payload, time_range),
        "collection_status": collection_status,
        "events": events,
        "resources": resources,
        "extensions": {},
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

    result_path = norm_dir / ("event.json" if job_type == "EVENT" else "canonical.json")
    dump_json(result_path, result)
    # PR4: Upload raw/normalized artifacts to S3
    bucket = payload["s3"]["bucket"]
    prefix = payload["s3"]["prefix"].rstrip("/")

    try:
        # storage_session은 "우리(DnDn) 계정" 권한으로 S3에 쓰는 세션.
        # (AssumeRole로 고객 계정에 들어갔더라도 S3는 우리 버킷에 저장해야 하므로 분리 권장)
        storage_session = boto3.Session()
        upload_tree_to_s3(storage_session, job_dir, bucket=bucket, prefix=prefix)
    except Exception as e:
        raise RuntimeError(f"S3 upload failed: {e}") from e
    return result_path
