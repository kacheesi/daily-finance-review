"""桌面报告同步：每次复盘完成后，把最新报告复制到桌面文件夹并更新 zip。
路径优先级：settings.json 的 desktop_sync.folder 和 desktop_path；默认桌面\每日市场复盘报告"""
import logging
import os
import shutil
import zipfile
from datetime import datetime

logger = logging.getLogger("daily_review.desktop_sync")

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _desktop() -> str:
    """定位桌面路径（支持 OneDrive 重定向）"""
    for cand in (os.path.join(os.path.expanduser("~"), "Desktop"),
                 os.path.join(os.path.expanduser("~"), "OneDrive", "Desktop")):
        if os.path.isdir(cand):
            return cand
    return os.path.expanduser("~")


def sync(report_dir: str = None) -> str:
    """同步 data/reports 下全部 HTML 到桌面文件夹（含 zip）。返回目标文件夹路径；失败返回空串。"""
    try:
        from src.utils.time_utils import load_settings
        cfg = load_settings().get("desktop_sync", {})
        enabled = cfg.get("enabled", True)
        if not enabled:
            return ""
        # 云端模式（GitHub Actions 等无桌面环境）跳过
        if os.environ.get("DAILY_REVIEW_CLOUD") == "1" or load_settings().get("cloud_mode", False):
            return ""
        folder = cfg.get("folder", "每日市场复盘报告")
        report_dir = report_dir or os.path.join(_PROJECT_ROOT, "data", "reports")

        target_dir = os.path.join(_desktop(), folder)
        os.makedirs(target_dir, exist_ok=True)

        files = [f for f in sorted(os.listdir(report_dir)) if f.endswith(".html")]
        if not files:
            return ""
        for f in files:
            shutil.copy2(os.path.join(report_dir, f), os.path.join(target_dir, f))

        # 更新 zip（覆盖旧包）
        zip_path = target_dir + ".zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in files:
                zf.write(os.path.join(target_dir, f), arcname=os.path.join(folder, f))

        with open(os.path.join(target_dir, "README.txt"), "w", encoding="utf-8") as f:
            f.write(f"共 {len(files)} 份报告 | 更新: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        logger.info("已同步 %d 份报告到桌面: %s", len(files), target_dir)
        return target_dir
    except Exception as e:
        logger.warning("桌面同步失败: %s", e)
        return ""
