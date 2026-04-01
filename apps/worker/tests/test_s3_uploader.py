from pathlib import Path

from dndn_worker.s3_uploader import upload_tree_to_s3


class FakeS3Client:
    def __init__(self) -> None:
        self.uploads: list[tuple[str, str, str, dict]] = []

    def upload_file(self, filename: str, bucket: str, key: str, ExtraArgs: dict) -> None:
        self.uploads.append((filename, bucket, key, ExtraArgs))


class FakeSession:
    def __init__(self, client: FakeS3Client) -> None:
        self._client = client

    def client(self, name: str) -> FakeS3Client:
        assert name == "s3"
        return self._client


def test_upload_tree_to_s3_skips_noise_and_sets_metadata(tmp_path: Path):
    (tmp_path / "nested").mkdir()
    (tmp_path / "hello.txt").write_text("hello", encoding="utf-8")
    (tmp_path / ".DS_Store").write_text("noise", encoding="utf-8")
    (tmp_path / "nested" / "._temp").write_text("noise", encoding="utf-8")
    (tmp_path / "nested" / "data.json").write_text('{"ok":true}', encoding="utf-8")

    fake_client = FakeS3Client()
    session = FakeSession(fake_client)

    uploaded = upload_tree_to_s3(
        session=session,
        local_root=tmp_path,
        bucket="worker-bucket",
        prefix="/artifacts/",
    )

    assert uploaded == [
        "s3://worker-bucket/artifacts/hello.txt",
        "s3://worker-bucket/artifacts/nested/data.json",
    ]
    assert fake_client.uploads[0][2] == "artifacts/hello.txt"
    assert fake_client.uploads[0][3]["ServerSideEncryption"] == "AES256"
    assert fake_client.uploads[0][3]["ContentType"] == "text/plain"
    assert fake_client.uploads[1][2] == "artifacts/nested/data.json"
    assert fake_client.uploads[1][3]["ContentType"] == "application/json"
