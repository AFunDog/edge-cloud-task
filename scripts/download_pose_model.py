from __future__ import annotations

import argparse
import shutil
from pathlib import Path
from urllib.request import urlopen


DEFAULT_MODEL = "yolo26n-pose.pt"
DEFAULT_URL_TEMPLATE = "https://github.com/ultralytics/assets/releases/latest/download/{model}"


def download_pose_model(model: str, dest: Path, url_template: str, overwrite: bool) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and not overwrite:
        print(f"已存在，跳过下载: {dest}")
        return dest

    url = url_template.format(model=model)
    tmp_path = dest.with_suffix(dest.suffix + ".tmp")
    print(f"下载 {model}")
    print(f"来源: {url}")
    print(f"保存到: {dest}")

    with urlopen(url) as response, tmp_path.open("wb") as output:
        shutil.copyfileobj(response, output)

    tmp_path.replace(dest)
    return dest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download an official Ultralytics pose model.")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="模型文件名，例如 yolo26n-pose.pt")
    parser.add_argument(
        "--dest",
        default="public/yolo-v26",
        help="保存目录或完整文件路径，默认保存到 public/yolo-v26/",
    )
    parser.add_argument(
        "--url-template",
        default=DEFAULT_URL_TEMPLATE,
        help="下载地址模板，默认指向 Ultralytics latest release asset",
    )
    parser.add_argument("--overwrite", action="store_true", help="覆盖已存在文件")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    dest = Path(args.dest)
    if dest.suffix.lower() != ".pt":
        dest = dest / args.model
    download_pose_model(args.model, dest, args.url_template, args.overwrite)


if __name__ == "__main__":
    main()
