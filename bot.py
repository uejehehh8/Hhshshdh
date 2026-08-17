#!/usr/bin/env python3
import os
import re
import sys
import time
import shutil
import asyncio
import logging
import subprocess
import urllib.parse

from aiogram import Bot, Dispatcher, Router, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import (
    Message, CallbackQuery, FSInputFile,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.filters import CommandStart, Command
from aiohttp import ClientTimeout
from aiogram.client.session.aiohttp import AiohttpSession

# ══════════════════════════════════════════════════════════════
#                    المتغيرات
# ══════════════════════════════════════════════════════════════

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "0").split(",") if x.strip()]
PUBLIC_BOT = True
MAX_FILE_SIZE = 50 * 1024 * 1024
MAX_DOWNLOAD_SIZE = 500 * 1024 * 1024
TEMP_DIR = os.path.join(os.path.expanduser("~"), "vt_bot_temp")
TIMEOUT = 600
VT_PATCHER_DIR = os.path.dirname(os.path.abspath(__file__))

# ══════════════════════════════════════════════════════════════

os.makedirs(TEMP_DIR, exist_ok=True)
SUPPORTED_EXT = (".apk", ".apks", ".xapk", ".apkm")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("VT_Bot")


class PatchStates(StatesGroup):
    selecting_patches = State()
    processing = State()


def is_authorized(user_id):
    if PUBLIC_BOT:
        return True
    return user_id in ADMIN_IDS


# ══════════════════════════════════════════════════════════════
#                      لوحات المفاتيح
# ══════════════════════════════════════════════════════════════

PATCH_OPTIONS = [
    ("ssl_bypass", "🔓 SSL Bypass"),
    ("remove_ads", "🚫 Remove Ads"),
    ("random_info", "📱 Random Info"),
    ("purchase", "💰 Purchase"),
    ("remove_ss", "📸 Remove SS"),
    ("remove_usb", "🔌 Remove USB"),
    ("spoof_pkg", "📦 Spoof PKG"),
    ("flutter_ssl", "🦋 Flutter SSL"),
    ("pairip", "🔒 Pairip"),
    ("tg_patch", "✈️ TG Patch"),
    ("aes_logs", "🔑 AES Logs"),
]

EXTRA_OPTIONS = [
    ("use_apkeditor", "🛠 APKEditor"),
    ("unsigned", "🔓 بدون توقيع"),
    ("hook_corex", "⚡ Hook CoreX"),
]


def get_patch_keyboard(selected):
    builder = InlineKeyboardBuilder()
    for key, label in PATCH_OPTIONS:
        is_on = selected.get(key, False)
        icon = "✅" if is_on else "⬜"
        builder.button(text=f"{icon} {label}", callback_data=f"toggle:{key}")
    builder.adjust(2)
    builder.row(
        InlineKeyboardButton(text="🔄 إعادة ضبط", callback_data="reset_patches"),
        InlineKeyboardButton(text="☑️ تحديد الكل", callback_data="select_all"),
    )
    builder.row(InlineKeyboardButton(text="⚙️ إعدادات إضافية", callback_data="extra_settings"))
    builder.row(InlineKeyboardButton(text="🚀 ابدأ التعديل", callback_data="start_patch"))
    builder.row(InlineKeyboardButton(text="❌ إلغاء", callback_data="cancel_patch"))
    return builder.as_markup()


def get_extra_keyboard(settings):
    builder = InlineKeyboardBuilder()
    for key, label in EXTRA_OPTIONS:
        is_on = settings.get(key, False)
        icon = "✅" if is_on else "⬜"
        builder.button(text=f"{icon} {label}", callback_data=f"setting:{key}")
    builder.adjust(1)
    builder.row(InlineKeyboardButton(text="🔙 رجوع", callback_data="back_to_patches"))
    return builder.as_markup()


def get_confirm_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ تأكيد", callback_data="confirm_patch"),
        InlineKeyboardButton(text="❌ إلغاء", callback_data="cancel_patch"),
    )
    return builder.as_markup()


# ══════════════════════════════════════════════════════════════
#                   تحميل APK من الروابط
# ══════════════════════════════════════════════════════════════

SUPPORTED_STORES = [
    "play.google.com",
    "apkpure.com",
    "apkcombo.com",
    "apkmirror.com",
    "apps.rustore.ru",
    "appgallery.huawei.com",
]


def extract_package_from_url(url):
    parsed = urllib.parse.urlparse(url)
    params = urllib.parse.parse_qs(parsed.query)
    if "play.google.com" in parsed.netloc:
        return params.get("id", [None])[0]
    if "apkpure.com" in parsed.netloc:
        parts = parsed.path.strip("/").split("/")
        if len(parts) >= 2:
            return parts[-1]
    if "apkcombo.com" in parsed.netloc:
        parts = parsed.path.strip("/").split("/")
        if len(parts) >= 2:
            return parts[-1]
    return None


def is_store_url(text):
    text = text.strip()
    if not text.startswith(("http://", "https://")):
        return False
    try:
        parsed = urllib.parse.urlparse(text)
        return any(store in parsed.netloc for store in SUPPORTED_STORES)
    except:
        return False


def download_apk_from_url(url, work_dir):
    import requests
    package_name = extract_package_from_url(url)
    if not package_name:
        return {"success": False, "error": "لم أتمكن من استخراج اسم الحزمة من الرابط"}
    apk_path = os.path.join(work_dir, f"{package_name}.apk")
    download_sources = [
        f"https://d.apkpure.net/b/APK/{package_name}?version=latest",
        f"https://d.cdnpure.com/b/APK/{package_name}?version=latest",
    ]
    headers = {
        "User-Agent": "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36"
    }
    for source_url in download_sources:
        try:
            resp = requests.get(source_url, headers=headers, stream=True, timeout=120, allow_redirects=True)
            if resp.status_code == 200 and int(resp.headers.get("content-length", 0)) > 10000:
                with open(apk_path, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=1024 * 64):
                        f.write(chunk)
                if os.path.getsize(apk_path) > 10000:
                    return {"success": True, "path": apk_path, "package": package_name, "size": os.path.getsize(apk_path)}
        except Exception:
            continue
    return {"success": False, "error": f"فشل تحميل {package_name}\nجرب حمّل الـ APK يدوياً وأرسله.", "package": package_name}


# ══════════════════════════════════════════════════════════════
#                       محرك الباتش
# ══════════════════════════════════════════════════════════════

def build_command(apk_path, selected, settings):
    cmd = [sys.executable, "-m", "VT_Patcher.APK_PATCHER", "-i", apk_path]
    cmd.append("-a")  # APKEditor دائماً على السيرفر
    if selected.get("remove_ads"):
        cmd.append("-rmads")
    if selected.get("random_info"):
        cmd.append("-r")
    if selected.get("purchase"):
        cmd.append("-P")
    if selected.get("remove_ss"):
        cmd.append("-rmss")
    if selected.get("remove_usb"):
        cmd.append("-rmusb")
    if selected.get("spoof_pkg"):
        cmd.append("-pkg")
    if selected.get("flutter_ssl"):
        cmd.append("-f")
    if selected.get("pairip"):
        cmd.append("-p")
    if selected.get("tg_patch"):
        cmd.append("-t")
    if selected.get("aes_logs"):
        cmd.append("-A")
    if settings.get("use_apkeditor"):
        pass  # already added
    if settings.get("unsigned"):
        cmd.append("-u")
    if settings.get("hook_corex"):
        cmd.extend(["-p", "-x"])
    return cmd


def run_patch(apk_path, selected, settings):
    start_time = time.time()
    try:
        cmd = build_command(apk_path, selected, settings)
        env = os.environ.copy()
        env["PYTHONPATH"] = VT_PATCHER_DIR + os.pathsep + env.get("PYTHONPATH", "")
        env["TERM"] = "xterm"
        logger.info(f"CMD: {' '.join(cmd)}")
        result = subprocess.run(cmd, cwd=VT_PATCHER_DIR, capture_output=True, text=True, timeout=TIMEOUT, env=env)
        elapsed = round(time.time() - start_time, 2)
        base_name = os.path.splitext(os.path.basename(apk_path))[0]
        expected_output = os.path.join(os.path.dirname(apk_path), f"{base_name}_Patched.apk")
        if os.path.exists(expected_output):
            return {"success": True, "output_path": expected_output, "time": elapsed}
        parent_dir = os.path.dirname(apk_path)
        for f in os.listdir(parent_dir):
            if "_Patched.apk" in f:
                return {"success": True, "output_path": os.path.join(parent_dir, f), "time": elapsed}
        home_dir = os.path.expanduser("~")
        for f in os.listdir(home_dir):
            if f.startswith(base_name) and f.endswith("_Patched.apk"):
                return {"success": True, "output_path": os.path.join(home_dir, f), "time": elapsed}
        error = ""
        if result.stderr:
            error = result.stderr[-1500:]
        elif result.stdout:
            error = result.stdout[-1500:]
        else:
            error = "لم يتم إنشاء ملف الإخراج"
        return {"success": False, "error": error, "time": elapsed}
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "انتهت المهلة (10 دقائق)", "time": TIMEOUT}
    except Exception as e:
        logger.error(f"Patch error: {e}")
        return {"success": False, "error": str(e), "time": round(time.time() - start_time, 2)}


# ══════════════════════════════════════════════════════════════
#                       الهاندلرات
# ══════════════════════════════════════════════════════════════

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    if not is_authorized(message.from_user.id):
        await message.answer("⛔ غير مصرح لك.")
        return
    await state.clear()
    await message.answer(
        "☠️ <b>VT_Patcher Bot</b> ☠️\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "🔧 <b>أداة تعديل ملفات APK</b>\n\n"
        "📌 <b>الاستخدام:</b>\n"
        "1️⃣ أرسل ملف APK أو رابط من المتجر\n"
        "2️⃣ اختر الباتشات\n"
        "3️⃣ انتظر واستلم\n\n"
        "🌐 <b>المتاجر المدعومة:</b>\n"
        "• Google Play\n"
        "• APKPure\n"
        "• APKCombo\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "👨‍💻 Dev: @VT_YC"
    )


@router.message(Command("help"))
async def cmd_help(message: Message):
    if not is_authorized(message.from_user.id):
        return
    await message.answer(
        "📖 <b>الباتشات:</b>\n\n"
        "🔓 SSL Bypass - تخطي SSL/VPN\n"
        "🚫 Remove Ads - إزالة الإعلانات\n"
        "📱 Random Info - تزوير الجهاز\n"
        "💰 Purchase - كسر الشراء\n"
        "📸 Remove SS - تخطي منع التصوير\n"
        "🔌 Remove USB - إزالة فحص USB\n"
        "📦 Spoof PKG - تزوير الحزمة\n"
        "🦋 Flutter SSL - تخطي Flutter\n"
        "🔒 Pairip - تخطي Pairip\n"
        "✈️ TG Patch - تعديل تليجرام\n"
        "🔑 AES Logs - حقن AES\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "📎 أرسل APK (حد 50MB) أو رابط متجر\n"
        "📢 @VT_YC"
    )


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("✅ تم الإلغاء. أرسل ملف جديد.")


@router.message(F.document)
async def handle_document(message: Message, state: FSMContext):
    if not is_authorized(message.from_user.id):
        await message.answer("⛔ غير مصرح لك.")
        return
    doc = message.document
    file_name = doc.file_name or "unknown.apk"
    file_ext = os.path.splitext(file_name)[1].lower()
    if file_ext not in SUPPORTED_EXT:
        await message.answer(f"⚠️ امتداد غير مدعوم: <code>{file_ext}</code>\nالمدعوم: {', '.join(SUPPORTED_EXT)}")
        return
    if doc.file_size and doc.file_size > MAX_FILE_SIZE:
        await message.answer(
            f"⚠️ الملف كبير: {doc.file_size//(1024*1024)} MB\n"
            f"📌 الحد: {MAX_FILE_SIZE//(1024*1024)} MB\n\n"
            f"💡 أرسل رابط التطبيق من المتجر بدلاً من ذلك:\n"
            f"<code>https://play.google.com/store/apps/details?id=com.example</code>"
        )
        return
    await state.update_data(
        file_id=doc.file_id,
        file_name=file_name,
        file_size=doc.file_size or 0,
        selected_patches={"ssl_bypass": True},
        extra_settings={},
    )
    await state.set_state(PatchStates.selecting_patches)
    size_mb = (doc.file_size or 0) / (1024 * 1024)
    await message.answer(
        f"📦 <b>تم استلام:</b> <code>{file_name}</code>\n"
        f"📏 <b>الحجم:</b> {size_mb:.2f} MB\n\n"
        f"🔧 <b>اختر الباتشات:</b>",
        reply_markup=get_patch_keyboard({"ssl_bypass": True})
    )


@router.message(F.text & ~F.text.startswith("/"))
async def handle_text(message: Message, state: FSMContext):
    if not is_authorized(message.from_user.id):
        return
    text = message.text.strip()
    if is_store_url(text):
        package_name = extract_package_from_url(text)
        await state.update_data(
            store_url=text,
            package_name=package_name,
            selected_patches={"ssl_bypass": True},
            extra_settings={},
        )
        await state.set_state(PatchStates.selecting_patches)
        await message.answer(
            f"🔗 <b>تم استلام الرابط:</b>\n\n"
            f"📦 <b>الحزمة:</b> <code>{package_name or 'غير معروف'}</code>\n"
            f"🌐 <b>المصدر:</b> {urllib.parse.urlparse(text).netloc}\n\n"
            f"🔧 <b>اختر الباتشات:</b>",
            reply_markup=get_patch_keyboard({"ssl_bypass": True})
        )
    else:
        await message.answer(
            "📎 أرسل ملف APK أو رابط من متجر مدعوم:\n\n"
            "• Google Play Store\n"
            "• APKPure\n"
            "• APKCombo\n\n"
            "مثال:\n<code>https://play.google.com/store/apps/details?id=com.example.app</code>"
        )


@router.callback_query(F.data.startswith("toggle:"))
async def toggle_patch(callback: CallbackQuery, state: FSMContext):
    key = callback.data.split(":")[1]
    data = await state.get_data()
    selected = data.get("selected_patches", {})
    selected[key] = not selected.get(key, False)
    await state.update_data(selected_patches=selected)
    await callback.message.edit_reply_markup(reply_markup=get_patch_keyboard(selected))
    await callback.answer()


@router.callback_query(F.data == "reset_patches")
async def reset_patches(callback: CallbackQuery, state: FSMContext):
    selected = {"ssl_bypass": True}
    await state.update_data(selected_patches=selected)
    await callback.message.edit_reply_markup(reply_markup=get_patch_keyboard(selected))
    await callback.answer("🔄 تم")


@router.callback_query(F.data == "select_all")
async def select_all(callback: CallbackQuery, state: FSMContext):
    all_p = {key: True for key, _ in PATCH_OPTIONS}
    await state.update_data(selected_patches=all_p)
    await callback.message.edit_reply_markup(reply_markup=get_patch_keyboard(all_p))
    await callback.answer("☑️ تم")


@router.callback_query(F.data == "extra_settings")
async def show_extra(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await callback.message.edit_reply_markup(reply_markup=get_extra_keyboard(data.get("extra_settings", {})))
    await callback.answer()


@router.callback_query(F.data.startswith("setting:"))
async def toggle_setting(callback: CallbackQuery, state: FSMContext):
    key = callback.data.split(":")[1]
    data = await state.get_data()
    settings = data.get("extra_settings", {})
    settings[key] = not settings.get(key, False)
    await state.update_data(extra_settings=settings)
    await callback.message.edit_reply_markup(reply_markup=get_extra_keyboard(settings))
    await callback.answer()


@router.callback_query(F.data == "back_to_patches")
async def back_to_patches(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await callback.message.edit_reply_markup(reply_markup=get_patch_keyboard(data.get("selected_patches", {})))
    await callback.answer()


@router.callback_query(F.data == "start_patch")
async def start_patch(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    selected = data.get("selected_patches", {})
    active = [k for k, v in selected.items() if v]
    if not active:
        await callback.answer("⚠️ اختر باتش واحد!", show_alert=True)
        return
    names = dict(PATCH_OPTIONS)
    patches_text = "\n".join(f"  • {names.get(p, p)}" for p in active)
    settings = data.get("extra_settings", {})
    settings_names = dict(EXTRA_OPTIONS)
    active_settings = [k for k, v in settings.items() if v]
    settings_text = ""
    if active_settings:
        settings_text = "\n\n⚙️ <b>إعدادات:</b>\n" + "\n".join(f"  • {settings_names.get(s, s)}" for s in active_settings)

    source = data.get("file_name") or data.get("package_name") or "غير معروف"
    await callback.message.edit_text(
        f"🚀 <b>ملخص:</b>\n\n"
        f"📄 <code>{source}</code>\n\n"
        f"🔧 <b>الباتشات ({len(active)}):</b>\n{patches_text}{settings_text}\n\n"
        f"❓ متابعة؟",
        reply_markup=get_confirm_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == "confirm_patch")
async def confirm_patch(callback: CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    user_id = callback.from_user.id
    await state.set_state(PatchStates.processing)
    status_msg = await callback.message.edit_text("⏳ <b>جاري التحميل...</b>")
    work_dir = os.path.join(TEMP_DIR, str(user_id), str(int(time.time())))
    os.makedirs(work_dir, exist_ok=True)

    try:
        # تحديد مصدر الملف
        if "file_id" in data:
            file_path = os.path.join(work_dir, data["file_name"])
            file_obj = await bot.get_file(data["file_id"])
            await bot.download_file(file_obj.file_path, file_path)

        elif "store_url" in data:
            await status_msg.edit_text(
                "⏳ <b>جاري التحميل من المتجر...</b>\n\n"
                f"📦 <code>{data.get('package_name', '')}</code>\n"
                "🔄 قد يستغرق بعض الوقت..."
            )
            dl_result = await asyncio.to_thread(download_apk_from_url, data["store_url"], work_dir)
            if not dl_result["success"]:
                safe_err = dl_result["error"].replace("<", "&lt;").replace(">", "&gt;")
                await status_msg.edit_text(f"❌ <b>فشل التحميل!</b>\n\n{safe_err}")
                await state.clear()
                return
            file_path = dl_result["path"]
            data["file_name"] = os.path.basename(file_path)
        else:
            await status_msg.edit_text("❌ لا يوجد ملف أو رابط.")
            await state.clear()
            return

        await status_msg.edit_text(
            "⏳ <b>جاري المعالجة...</b>\n\n"
            "✅ تم التحميل\n"
            "🔄 تطبيق الباتشات...\n\n"
            "💡 <i>قد تأخذ عدة دقائق</i>"
        )

        selected = data.get("selected_patches", {})
        settings = data.get("extra_settings", {})
        result = await asyncio.to_thread(run_patch, file_path, selected, settings)

        if result["success"]:
            output_path = result["output_path"]
            output_size = os.path.getsize(output_path)
            output_size_mb = output_size / (1024 * 1024)

            if output_size > MAX_FILE_SIZE:
                await status_msg.edit_text(
                    f"✅ <b>تم التعديل!</b>\n\n"
                    f"📄 <code>{os.path.basename(output_path)}</code>\n"
                    f"📏 الحجم: {output_size_mb:.1f} MB\n\n"
                    f"⚠️ الملف أكبر من {MAX_FILE_SIZE//(1024*1024)}MB (حد تليجرام)\n"
                    f"لا يمكن إرساله. جرب باتشات أقل."
                )
                return

            await status_msg.edit_text("⏳ 📤 جاري رفع الملف...")
            output_file = FSInputFile(output_path, filename=os.path.basename(output_path))
            active_patches = [k for k, v in selected.items() if v]
            names = dict(PATCH_OPTIONS)
            patches_list = ", ".join(names.get(p, p).split(" ", 1)[-1] for p in active_patches[:5])
            if len(active_patches) > 5:
                patches_list += f" +{len(active_patches)-5}"

            await bot.send_document(
                chat_id=user_id,
                document=output_file,
                caption=(
                    f"✅ <b>تم بنجاح!</b>\n\n"
                    f"📄 <code>{os.path.basename(output_path)}</code>\n"
                    f"📏 {output_size_mb:.2f} MB\n"
                    f"⏱ {result['time']} ثانية\n"
                    f"🔧 {patches_list}\n\n"
                    f"☠️ VT_Patcher | @VT_YC"
                ),
            )
            await status_msg.delete()
        else:
            error_text = result.get("error", "خطأ غير معروف")
            error_text = re.sub(r'\033\[[0-9;]*m', '', error_text)
            error_text = error_text.replace("<", "&lt;").replace(">", "&gt;")
            if len(error_text) > 800:
                error_text = error_text[-800:]
            await status_msg.edit_text(
                f"❌ <b>فشل!</b>\n\n"
                f"⏱ {result.get('time', '?')} ثانية\n\n"
                f"<code>{error_text}</code>\n\n"
                f"💡 جرب باتشات أقل أو أرسل الملف مرة أخرى."
            )

    except Exception as e:
        logger.error(f"Error: {e}")
        try:
            safe_error = str(e)[:500].replace("<", "&lt;").replace(">", "&gt;")
            await status_msg.edit_text(f"❌ <b>خطأ:</b>\n<code>{safe_error}</code>")
        except:
            try:
                await status_msg.edit_text("❌ حدث خطأ.", parse_mode=None)
            except:
                pass
    finally:
        try:
            if os.path.exists(work_dir):
                shutil.rmtree(work_dir, ignore_errors=True)
        except:
            pass
        await state.clear()


@router.callback_query(F.data == "cancel_patch")
async def cancel_patch(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ تم الإلغاء. أرسل ملف جديد.")
    await callback.answer()


# ══════════════════════════════════════════════════════════════
#                       التشغيل
# ══════════════════════════════════════════════════════════════

async def main():
    if not BOT_TOKEN:
        print("❌ ضع BOT_TOKEN في المتغيرات!")
        sys.exit(1)
    vt_path = os.path.join(VT_PATCHER_DIR, "VT_Patcher")
    if not os.path.isdir(vt_path):
        print(f"❌ مجلد VT_Patcher/ غير موجود في: {VT_P
