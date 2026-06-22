import os
import oss2
import yaml
from dotenv import load_dotenv

load_dotenv()
CFG = yaml.safe_load(open("config/config.yaml", encoding="utf-8"))


def _bucket():
    auth = oss2.Auth(os.environ["OSS_ACCESS_KEY_ID"], os.environ["OSS_ACCESS_KEY_SECRET"])
    return oss2.Bucket(auth, "https://" + CFG["oss"]["endpoint"], CFG["oss"]["bucket"])


def upload_bytes(key: str, data: bytes):
    """内网上传到 OSS，免流量费。"""
    _bucket().put_object(key, data)


def download_text(key: str) -> str:
    return _bucket().get_object(key).read().decode("utf-8")


def list_keys(prefix: str):
    return [o.key for o in oss2.ObjectIterator(_bucket(), prefix=prefix)]
