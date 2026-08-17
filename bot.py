#!/usr/bin/env python3
"""
══════════════════════════════════════════════════════════════
  VT_Patcher Telegram Bot v2.0.0
  Developer: Joker|M4
  Channel: @VT_YC
══════════════════════════════════════════════════════════════
"""

import os
import re
import sys
import time
import shutil
import asyncio
import logging
import subprocess

from aiogram import Bot, Dispatcher, Router, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import (
    Message, CallbackQuery, FSInputFile,
    InlineKeyboardButton
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.filters import CommandStart, Command


# ══════════════════════════════════════════════════════════════
#                    المتغيرات - عدّلها
# ══════════════════════════════════════════════════════════════

BOT_TOKEN = "8757581045:AAF6c-XB9xdXdyLlOtVx4Er3ve5TTH8J8R0"

ADMIN_IDS = [8588392906]

PUBLIC_BOT = True

MAX_FILE_SIZE = 50 * 1024 * 1024

TEMP_DIR = os.path.join(os.path.expanduser("~"), "vt_bot_temp")

TIMEOUT = 600

VT_PATCHER_DIR = os.path.dirname(os.path.abspath(__file__))

# ══════════════════════════════════════════════════════════════

os.makedirs(TEMP_DIR, exist_ok=True)
SUPPORTED_EXT = (".apk", ".apks", ".xapk", ".apkm")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("VT_Bot")


# ══════════════════════════════════════════════════════════════
#                         الحالات
# ══════════════════════════════════════════════════════════════

class PatchStates(StatesGroup):
    selecting_patches = State()
    processing = State()


# ══════════════════════════════════════════════════════════════
#                      الصلاحيات
# ══════════════════════════════════════════════════════════════

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
#                       محرك الباتش
# ══════════════════════════════════════════════════════════════

def build_command(apk_path, selected, settings):
    cmd = [sys.executable, "-m", "VT_Patcher.APK_PATCHER", "-i", apk_path]
    
    # === تفعيل APKEditor دائماً (لتجنب مشاكل aapt2) ===
    cmd.append("-a")
    
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
    # settings.get("use_apkeditor") تم تفعيله افتراضياً
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
        logger.info(f"CMD: {' '.join(cmd)}")
        result = subprocess.run(
            cmd,
            cwd=VT_PATCHER_DIR,
            capture_output=True,
            text=True,
            timeout=TIMEOUT,
            env=env
        )
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
        "1️⃣ أرسل ملف APK\n"
        "2️⃣ اختر الباتشات\n"
        "3️⃣ انتظر واستلم\n\n"
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
        "⚠️ الحد: 50 MB | @VT_YC"
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
        await message.answer(f"⚠️ الملف كبير: {doc.file_size//(1024*1024)} MB\nالحد: 50 MB")
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
async def handle_text(message: Message):
    if not is_authorized(message.from_user.id):
        return
    await message.answer("📎 أرسل ملف APK للبدء.")


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
    await callback.message.edit_text(
        f"🚀 <b>ملخص:</b>\n\n"
        f"📄 <code>{data.get('file_name')}</code>\n\n"
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
    file_path = os.path.join(work_dir, data["file_name"])
    try:
        file_obj = await bot.get_file(data["file_id"])
        await bot.download_file(file_obj.file_path, file_path)
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
            output_size = os.path.getsize(output_path) / (1024 * 1024)
            if os.path.getsize(output_path) > MAX_FILE_SIZE:
                await status_msg.edit_text(
                    f"⚠️ الملف المعدل كبير: {output_size:.1f} MB\n"
                    f"حد تليجرام 50 MB. جرب باتشات أقل."
                )
                return
            await status_msg.edit_text(
                "⏳ <b>جاري الرفع...</b>\n\n"
                "✅ تم التحميل\n"
                "✅ تم التعديل\n"
                "📤 رفع الملف..."
            )
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
                    f"📏 {output_size:.2f} MB\n"
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
                f"💡 جرب APKEditor من الإعدادات أو قلل الباتشات."
            )
    except Exception as e:
        logger.error(f"Error: {e}")
        try:
            safe_error = str(e)[:500].replace("<", "&lt;").replace(">", "&gt;")
            await status_msg.edit_text(f"❌ <b>خطأ:</b>\n<code>{safe_error}</code>")
        except:
            try:
                await status_msg.edit_text("❌ حدث خطأ أثناء المعالجة.", parse_mode=None)
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
    if "xxxx" in BOT_TOKEN:
        print("❌ عدّل BOT_TOKEN في الملف!")
        sys.exit(1)
    vt_path = os.path.join(VT_PATCHER_DIR, "VT_Patcher")
    if not os.path.isdir(vt_path):
        print(f"❌ مجلد VT_Patcher/ غير موجود في: {VT_PATCHER_DIR}")
        sys.exit(1)
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    logger.info("☠️ VT_Patcher Bot Started! | @VT_YC")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped.")
