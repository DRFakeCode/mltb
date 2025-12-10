from html import escape
from psutil import virtual_memory, cpu_percent, disk_usage
from time import time
from asyncio import iscoroutinefunction, gather

from ... import task_dict, task_dict_lock, bot_start_time, status_dict, DOWNLOAD_DIR
from ...core.config_manager import Config
from ..telegram_helper.button_build import ButtonMaker

SIZE_UNITS = ["B", "KB", "MB", "GB", "TB", "PB"]


class MirrorStatus:
    STATUS_UPLOAD = "Upload"
    STATUS_DOWNLOAD = "Download"
    STATUS_CLONE = "Clone"
    STATUS_QUEUEDL = "QueueDl"
    STATUS_QUEUEUP = "QueueUp"
    STATUS_PAUSED = "Pause"
    STATUS_ARCHIVE = "Archive"
    STATUS_EXTRACT = "Extract"
    STATUS_SPLIT = "Split"
    STATUS_CHECK = "CheckUp"
    STATUS_SEED = "Seed"
    STATUS_SAMVID = "SamVid"
    STATUS_CONVERT = "Convert"
    STATUS_FFMPEG = "FFmpeg"


STATUSES = {
    "ALL": "All",
    "DL": MirrorStatus.STATUS_DOWNLOAD,
    "UP": MirrorStatus.STATUS_UPLOAD,
    "QD": MirrorStatus.STATUS_QUEUEDL,
    "QU": MirrorStatus.STATUS_QUEUEUP,
    "AR": MirrorStatus.STATUS_ARCHIVE,
    "EX": MirrorStatus.STATUS_EXTRACT,
    "SD": MirrorStatus.STATUS_SEED,
    "CL": MirrorStatus.STATUS_CLONE,
    "CM": MirrorStatus.STATUS_CONVERT,
    "SP": MirrorStatus.STATUS_SPLIT,
    "SV": MirrorStatus.STATUS_SAMVID,
    "FF": MirrorStatus.STATUS_FFMPEG,
    "PA": MirrorStatus.STATUS_PAUSED,
    "CK": MirrorStatus.STATUS_CHECK,
}


async def get_task_by_gid(gid: str):
    async with task_dict_lock:
        for tk in task_dict.values():
            if hasattr(tk, "seeding"):
                await tk.update()
            if tk.gid() == gid:
                return tk
        return None


async def get_specific_tasks(status, user_id):
    if status == "All":
        if user_id:
            return [tk for tk in task_dict.values() if tk.listener.user_id == user_id]
        else:
            return list(task_dict.values())
    tasks_to_check = (
        [tk for tk in task_dict.values() if tk.listener.user_id == user_id]
        if user_id
        else list(task_dict.values())
    )
    coro_tasks = []
    coro_tasks.extend(tk for tk in tasks_to_check if iscoroutinefunction(tk.status))
    coro_statuses = await gather(*[tk.status() for tk in coro_tasks])
    result = []
    coro_index = 0
    for tk in tasks_to_check:
        if tk in coro_tasks:
            st = coro_statuses[coro_index]
            coro_index += 1
        else:
            st = tk.status()
        if (st == status) or (
            status == MirrorStatus.STATUS_DOWNLOAD and st not in STATUSES.values()
        ):
            result.append(tk)
    return result


async def get_all_tasks(req_status: str, user_id):
    async with task_dict_lock:
        return await get_specific_tasks(req_status, user_id)


def get_readable_file_size(size_in_bytes):
    if not size_in_bytes:
        return "0B"

    index = 0
    while size_in_bytes >= 1024 and index < len(SIZE_UNITS) - 1:
        size_in_bytes /= 1024
        index += 1

    return f"{size_in_bytes:.2f}{SIZE_UNITS[index]}"


def get_readable_time(seconds: int):
    periods = [("d", 86400), ("h", 3600), ("m", 60), ("s", 1)]
    result = ""
    for period_name, period_seconds in periods:
        if seconds >= period_seconds:
            period_value, seconds = divmod(seconds, period_seconds)
            result += f"{int(period_value)}{period_name}"
    return result


def time_to_seconds(time_duration):
    try:
        parts = time_duration.split(":")
        if len(parts) == 3:
            hours, minutes, seconds = map(float, parts)
        elif len(parts) == 2:
            hours = 0
            minutes, seconds = map(float, parts)
        elif len(parts) == 1:
            hours = 0
            minutes = 0
            seconds = float(parts[0])
        else:
            return 0
        return hours * 3600 + minutes * 60 + seconds
    except:
        return 0


def speed_string_to_bytes(size_text: str):
    size = 0
    size_text = size_text.lower()
    if "k" in size_text:
        size += float(size_text.split("k")[0]) * 1024
    elif "m" in size_text:
        size += float(size_text.split("m")[0]) * 1048576
    elif "g" in size_text:
        size += float(size_text.split("g")[0]) * 1073741824
    elif "t" in size_text:
        size += float(size_text.split("t")[0]) * 1099511627776
    elif "b" in size_text:
        size += float(size_text.split("b")[0])
    return size


def get_progress_bar_string(pct):
    pct = float(pct.strip("%"))
    p = min(max(pct, 0), 100)
    cFull = int(p // 8)
    p_str = "▰" * cFull
    p_str += "▱" * (12 - cFull)
    return f"[{p_str}]"


async def get_readable_message(sid, is_user, page_no=1, status="All", page_step=1):
    msg = ""
    button = None
    tasks = await get_specific_tasks(status, sid if is_user else None)
    STATUS_LIMIT = Config.STATUS_LIMIT
    tasks_no = len(tasks)
    pages = (max(tasks_no, 1) + STATUS_LIMIT - 1) // STATUS_LIMIT
    if page_no > pages:
        page_no = (page_no - 1) % pages + 1
        status_dict[sid]["page_no"] = page_no
    elif page_no < 1:
        page_no = pages - (abs(page_no) % pages)
        status_dict[sid]["page_no"] = page_no
    start_position = (page_no - 1) * STATUS_LIMIT

    for index, task in enumerate(
        tasks[start_position : STATUS_LIMIT + start_position], start=1
    ):
        tstatus = await task.status() if iscoroutinefunction(task.status) else task.status()
        
        # Safe Attribute Access
        is_qbit = getattr(task.listener, 'is_qbit', False)
        is_aria2 = getattr(task.listener, 'is_aria2', False)
        is_ytdlp = getattr(task.listener, 'is_ytdlp', False)
        is_leech = getattr(task.listener, 'is_leech', False)
        is_torrent = getattr(task.listener, 'is_torrent', False)

        # Elapsed Time
        elapsed = "نامشخص"
        try:
            if hasattr(task.listener.message, 'date'):
                elapsed = get_readable_time(time() - task.listener.message.date.timestamp())
        except:
            pass

        # Engine Name
        if is_qbit:
            engine = "qBittorrent"
        elif is_aria2:
            engine = "Aria2"
        elif is_ytdlp:
            engine = "Yt-dlp"
        else:
            engine = "FFmpeg/Tg"

        # Mode Name
        mode = "#Leech" if is_leech else "#Mirror"
        if hasattr(task.listener, 'is_zip') and task.listener.is_zip:
            mode += " (Zip)"
        elif hasattr(task.listener, 'extract') and task.listener.extract:
             mode += " (Unzip)"

        # Get User Name
        try:
            user_name = task.listener.message.from_user.first_name
        except:
            user_name = "User"

        # --- BUILDING THE MESSAGE ---
        # Define the invisible Left-to-Right Mark
        LRM = '\u200E' 

        # 1. Filename
        msg += f"<b>{index + start_position}.</b> <code>{escape(f'{task.name()}')}</code>\n"
        
        # 2. Header
        msg += f"<b>{LRM}╭ {user_name} {LRM}← تسک توسط</b>\n"

        if tstatus not in [MirrorStatus.STATUS_SEED, MirrorStatus.STATUS_QUEUEUP] and task.listener.progress:
            progress = task.progress()
            
            # 3. Progress Bar
            msg += f"<b>{LRM}├ {get_progress_bar_string(progress)} {progress}</b>\n"
            
            # 4. Stats Tree
            # We add {LRM} before the arrow (←) to separate the Persian Unit from the Persian Label
            msg += f"<b>{LRM}├ <a href='{task.listener.message.link}'>{tstatus}</a> {LRM}← وضعیت</b>\n"
            msg += f"<b>{LRM}├ {task.processed_bytes()} {LRM}← پردازش شده</b>\n"
            msg += f"<b>{LRM}├ {task.size()} {LRM}← حجم کل</b>\n"
            msg += f"<b>{LRM}├ {task.speed()} {LRM}← سرعت</b>\n"
            msg += f"<b>{LRM}├ {task.eta()} {LRM}← زمان باقیمانده</b>\n"
            msg += f"<b>{LRM}├ {elapsed} {LRM}← زمان سپری شده</b>\n"
            msg += f"<b>{LRM}├ {engine} {LRM}← موتور</b>\n"
            msg += f"<b>{LRM}├ {mode} {LRM}← حالت</b>\n"
            
            if tstatus == MirrorStatus.STATUS_DOWNLOAD and (is_torrent or is_qbit):
                try:
                    msg += f"<b>{LRM}├ {task.seeders_num()}/{task.leechers_num()} {LRM}← سیدر/لیچر</b>\n"
                except:
                    pass
                    
        elif tstatus == MirrorStatus.STATUS_SEED:
            msg += f"<b>{LRM}├ <a href='{task.listener.message.link}'>{tstatus}</a> {LRM}← وضعیت</b>\n"
            msg += f"<b>{LRM}├ {task.size()} {LRM}← حجم</b>\n"
            msg += f"<b>{LRM}├ {task.seed_speed()} {LRM}← سرعت آپلود</b>\n"
            msg += f"<b>{LRM}├ {task.uploaded_bytes()} {LRM}← آپلود شده</b>\n"
            msg += f"<b>{LRM}├ {task.ratio()} {LRM}← ضریب</b>\n"
            msg += f"<b>{LRM}├ {task.seeding_time()} {LRM}← زمان</b>\n"
        else:
            msg += f"<b>{LRM}├ <a href='{task.listener.message.link}'>{tstatus}</a> {LRM}← وضعیت</b>\n"
            msg += f"<b>{LRM}├ {task.size()} {LRM}← حجم</b>\n"

        # 5. Cancel Command
        try:
            short_gid = task.gid()[:12]
            msg += f"<b>{LRM}╰ /c_{short_gid} {LRM}← توقف</b>\n\n"
        except:
             msg += f"<b>{LRM}╰ /cancel {LRM}← توقف</b>\n\n"

    if len(msg) == 0:
        if status == "All":
            return None, None
        else:
            msg = f"هیچ وظیفه {status} فعالی وجود ندارد!\n\n"

    # Buttons (No Changes)
    buttons = ButtonMaker()
    if not is_user:
        buttons.data_button("📜", f"status {sid} ov", position="header")
    if len(tasks) > STATUS_LIMIT:
        msg += f"<b>صفحه:</b> {page_no}/{pages} | <b>تعداد:</b> {tasks_no} | <b>گام:</b> {page_step}\n"
        buttons.data_button("<<", f"status {sid} pre", position="header")
        buttons.data_button(">>", f"status {sid} nex", position="header")
        if tasks_no > 30:
            for i in [1, 2, 4, 6, 8, 10, 15]:
                buttons.data_button(i, f"status {sid} ps {i}", position="footer")
    if status != "All" or tasks_no > 20:
        for label, status_value in list(STATUSES.items()):
            if status_value != status:
                buttons.data_button(label, f"status {sid} st {status_value}")
    buttons.data_button("♻️", f"status {sid} ref", position="header")
    button = buttons.build_menu(8)
    
    msg += f"<b>پردازنده:</b> {cpu_percent()}% | <b>آزاد:</b> {get_readable_file_size(disk_usage(DOWNLOAD_DIR).free)}"
    msg += f"\n<b>رم:</b> {virtual_memory().percent}% | <b>فعالیت:</b> {get_readable_time(time() - bot_start_time)}"
    
    return msg, button