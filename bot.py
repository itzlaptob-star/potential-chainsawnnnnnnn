import asyncio
import logging
import time
import os
import uuid
import firebase_admin
from firebase_admin import credentials, db as firebase_db
from aiogram import Bot, Dispatcher, types, F, BaseMiddleware
from aiogram.filters import CommandStart, CommandObject
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, 
    InlineKeyboardButton, WebAppInfo, MenuButtonWebApp, Message, CallbackQuery, FSInputFile
)
from aiogram.exceptions import TelegramForbiddenError, TelegramUnauthorizedError, TelegramRetryAfter, TelegramAPIError

# --- ১. Firebase কানেকশন সেটআপ ---
if not firebase_admin._apps:
    cred = credentials.Certificate("serviceAccountKey.json")
    firebase_admin.initialize_app(cred, {
        'databaseURL': 'https://tiktokviralbot-4430e-default-rtdb.firebaseio.com/' 
    })

# --- ২. ট্রাফিক পুলিশ (Rate Limiter) Middleware ---
class TrafficPoliceMiddleware(BaseMiddleware):
    def __init__(self, limit: int = 25):
        self.limit = limit
        self.request_times = []
        super().__init__()

    async def __call__(self, handler, event, data):
        current_time = time.time()
        # গত ১ সেকেন্ডের রিকোয়েস্ট উইন্ডো চেক করা
        self.request_times = [t for t in self.request_times if current_time - t < 1.0]
        
        if len(self.request_times) >= self.limit:
            await asyncio.sleep(0.1) 
            return await self.__call__(handler, event, data)
        
        self.request_times.append(current_time)
        return await handler(event, data)

# --- ৩. কনফিগারেশন ও বট সেটআপ ---
TOKEN = "8533223944:AAGc83yohtzBwWKQr06xJtVy7rmoEKHY58w" 
ADMIN_LIST = [7848481158, 8327414180] 
WEB_APP_URL = "https://tiktokbot3.pages.dev/" 

bot = Bot(token=TOKEN)
dp = Dispatcher()

# ট্রাফিক পুলিশ ইন্সট্যান্স গ্লোবালি হ্যান্ডেল করা
traffic_manager = TrafficPoliceMiddleware(limit=25)
dp.message.outer_middleware(traffic_manager)

# --- ৪. FSM States ---
class VideoUpload(StatesGroup):
    name = State()
    photo = State()
    category = State()
    video_source = State()

class VideoDelete(StatesGroup):
    waiting_for_search = State()
    confirm_selection = State()

class BotNotice(StatesGroup):
    waiting_for_payload = State()

# --- ৫. কিবোর্ড ফাংশনসমূহ (এডমিন ও ইউজার) ---
def get_admin_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="➕ Add Video"), KeyboardButton(text="🔕 Delete Video")],
        [KeyboardButton(text="📢 BOT NOTICE"), KeyboardButton(text="🔙 Back to Menu")]
    ], resize_keyboard=True)

def get_back_kb():
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="🔙 Back to Menu")]], resize_keyboard=True)

def get_category_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="BP S5")],
        [KeyboardButton(text="🔙 Back to Menu")]
    ], resize_keyboard=True)

# --- ৬. সাপ্তাহিক অটোমেটিক ব্যাকআপ ফাংশন ---
async def send_weekly_backup():
    while True:
        await asyncio.sleep(604800) # ৭ দিন পর পর
        for admin_id in ADMIN_LIST:
            try:
                data = firebase_db.reference('/').get()
                backup_filename = "firebase_backup.json"
                with open(backup_filename, "w", encoding="utf-8") as f:
                    import json
                    json.dump(data, f, indent=4)
                
                db_file = FSInputFile(backup_filename)
                await bot.send_document(
                    chat_id=admin_id, 
                    document=db_file, 
                    caption="📅 <b>সাপ্তাহিক ডাটাবেজ ব্যাকআপ</b>\n\n✅ আপনার ক্লাউড ডাটাবেজ ব্যাকআপ সফল হয়েছে।"
                )
            except:
                pass

# --- ৭. স্টার্ট হ্যান্ডলার ও মেনু লজিক ---
@dp.message(CommandStart())
@dp.message(F.text == "🔙 Back to Menu")
async def start_handler(message: Message, command: CommandObject = None, state: FSMContext = None):
    if state: await state.clear()
    user_id = str(message.from_user.id)
    
    # ইউজার সেভ করা
    user_ref = firebase_db.reference(f'users/{user_id}')
    if not user_ref.get():
        user_ref.set({'joined_at': time.time()})

    try:
        await bot.set_chat_menu_button(
            chat_id=int(user_id), 
            menu_button=MenuButtonWebApp(text="Watch Now 🎬", web_app=WebAppInfo(url=WEB_APP_URL))
        )
    except:
        pass

    # ভিডিও ডিপ-লিংক হ্যান্ডেলিং
    if command and command.args:
        video_id = command.args
        v_data = firebase_db.reference(f'videos/{video_id}').get()
        
        if v_data:
            try:
                await bot.send_video(
                    chat_id=int(user_id), 
                    video=v_data['video'], 
                    caption=f"🎬 <b>{v_data['name']}</b>", 
                    parse_mode="HTML",
                    protect_content=False 
                )
            except:
                pass
            return

    user_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎬 Watch Now (Web App)", web_app=WebAppInfo(url=WEB_APP_URL))]
    ])

    try:
        await message.answer(
            "<b>আসসালামুয়ালাইকুম</b> 🥰\n\nআমাদের বট ২৪ ঘন্টা সচল। ভিডিও ডাউনলোড করতে নিচের <b>Watch Now</b> বাটনে ক্লিক করুন 🥰",
            reply_markup=user_kb,
            parse_mode="HTML"
        )
    except:
        pass
    
    if int(user_id) in ADMIN_LIST:
        await message.answer("🛠 এডমিন প্যানেল সচল করা হয়েছে:", reply_markup=get_admin_kb())

# --- ৮. ভিডিও অ্যাড করার সেকশন ---
@dp.message(F.text == "➕ Add Video")
async def add_v_start(message: Message, state: FSMContext):
    if message.from_user.id in ADMIN_LIST:
        await state.set_state(VideoUpload.name)
        await message.answer("📝 ভিডিওর টাইটেল লিখুন (Episode 01):", reply_markup=get_back_kb())

@dp.message(VideoUpload.name)
async def add_v_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    await state.set_state(VideoUpload.photo)
    await message.answer("🖼 থাম্বনেইল পাঠান (ফটো অথবা ডাইরেক্ট ইউআরএল):", reply_markup=get_back_kb())

@dp.message(VideoUpload.photo)
async def add_v_photo(message: Message, state: FSMContext):
    if message.photo:
        file = await bot.get_file(message.photo[-1].file_id)
        photo_url = f"https://api.telegram.org/file/bot{TOKEN}/{file.file_path}"
        await state.update_data(photo=photo_url)
    else:
        await state.update_data(photo=message.text)
    
    await state.set_state(VideoUpload.category)
    await message.answer("📂 ক্যাটাগরি সিলেক্ট করুন:", reply_markup=get_category_kb())

@dp.message(VideoUpload.category)
async def add_v_cat(message: Message, state: FSMContext):
    await state.update_data(category=message.text)
    await state.set_state(VideoUpload.video_source)
    await message.answer("🎬 এখন ভিডিও ফাইলটি সেন্ড করুন:", reply_markup=get_back_kb())

@dp.message(VideoUpload.video_source, F.video)
async def add_v_final(message: Message, state: FSMContext):
    data = await state.get_data()
    v_id = str(uuid.uuid4())[:8]
    
    firebase_db.reference(f'videos/{v_id}').set({
        'id': v_id,
        'name': data['name'],
        'photo': data['photo'],
        'video': message.video.file_id,
        'category': data['category']
    })
    
    await message.answer(f"✅ ভিডিও যুক্ত হয়েছে! আইডি: `{v_id}`", reply_markup=get_admin_kb())
    await state.clear()

# --- ৯. ভিডিও ডিলিট করার সেকশন ---
@dp.message(F.text == "🔕 Delete Video")
async def delete_v_init(message: Message, state: FSMContext):
    if message.from_user.id in ADMIN_LIST:
        await state.set_state(VideoDelete.waiting_for_search)
        await message.answer("🔍 ডিলিট করতে চাওয়া ভিডিওর নাম লিখুন:", reply_markup=get_back_kb())

@dp.message(VideoDelete.waiting_for_search)
async def delete_v_search_results(message: Message, state: FSMContext):
    query = message.text.lower()
    videos_ref = firebase_db.reference('videos').get()
    
    if not videos_ref:
        await message.answer("❌ কোনো ভিডিও পাওয়া যায়নি।")
        return

    matches = [v for v in videos_ref.values() if query in v['name'].lower()]
    
    if not matches:
        await message.answer("❌ কোনো ভিডিও পাওয়া যায়নি।")
        return

    buttons = [[InlineKeyboardButton(text=f"🗑 {v['name']}", callback_data=f"askdel_{v['id']}")] for v in matches]
    buttons.append([InlineKeyboardButton(text="❌ বাতিল", callback_data="cancel_del")])
    
    await message.answer(f"🔎 {len(matches)}টি ভিডিও পাওয়া গেছে। কোনটি মুছবেন?", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await state.set_state(VideoDelete.confirm_selection)

@dp.callback_query(F.data.startswith("askdel_"), VideoDelete.confirm_selection)
async def delete_v_ask_confirm(callback: CallbackQuery):
    vid_id = callback.data.split("_")[1]
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ হ্যা, মুছুন", callback_data=f"dodel_{vid_id}")],
        [InlineKeyboardButton(text="🔙 ফিরে যান", callback_data="cancel_del")]
    ])
    await callback.message.edit_text("⚠️ আপনি কি নিশ্চিতভাবে ভিডিওটি ডিলিট করতে চান?", reply_markup=kb)

@dp.callback_query(F.data.startswith("dodel_"), VideoDelete.confirm_selection)
async def delete_v_execute(callback: CallbackQuery, state: FSMContext):
    vid_id = callback.data.split("_")[1]
    firebase_db.reference(f'videos/{vid_id}').delete()
    await callback.message.edit_text("✅ ভিডিওটি সফলভাবে মুছে ফেলা হয়েছে।")
    await state.clear()

@dp.callback_query(F.data == "cancel_del")
async def delete_v_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    try: await callback.message.delete()
    except: pass

# --- ১০. হাই-প্রফেশনাল ব্যালেন্সড ব্রডকাস্ট সিস্টেম ---
@dp.message(F.text == "📢 BOT NOTICE")
async def notice_init(message: Message, state: FSMContext):
    if message.from_user.id in ADMIN_LIST:
        await state.set_state(BotNotice.waiting_for_payload)
        await message.answer("📢 নোটিশ মেসেজটি দিন (টেক্সট/ছবি/ভিডিও):", reply_markup=get_back_kb())

@dp.message(BotNotice.waiting_for_payload)
async def notice_broadcast(message: Message, state: FSMContext):
    users_ref = firebase_db.reference('users').get()
    if not users_ref:
        await message.answer("❌ কোনো ইউজার পাওয়া যায়নি।")
        await state.clear()
        return

    users = list(users_ref.keys())
    total_users = len(users)
    sent_count = 0
    failed_count = 0
    traffic_police = 0
    start_time = time.time()
    
    # ট্রাফিক পুলিশ লিমিট ২৫ রাখা হয়েছে যাতে ভারসাম্য বজায় থাকে
    traffic_manager.limit = 25 
    
    progress_msg = await message.answer(
        f"🚀 **ব্রডকাস্ট মিশন শুরু হয়েছে...**\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📊 টার্গেট ইউজার: `{total_users}` জন\n"
        f"⏳ অবস্থা: ব্যালেন্সড স্পিডে প্রসেসিং হচ্ছে..."
    )

    for uid in users:
        try: 
            # মেসেজ কপি করে পাঠানো
            await message.copy_to(chat_id=int(uid))
            sent_count += 1
            traffic_police += 1
        except (TelegramForbiddenError, TelegramUnauthorizedError):
            failed_count += 1
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after)
            await message.copy_to(chat_id=int(uid))
            sent_count += 1
        except Exception:
            failed_count += 1
            
        # প্রতি ১০ জন পরপর লাইভ আপডেট (বট স্মুথ রাখার জন্য)
        if sent_count % 10 == 0 or sent_count == total_users:
            percentage = (sent_count / total_users) * 100
            bar_len = int(percentage / 10)
            progress_bar = "▓" * bar_len + "░" * (10 - bar_len)
            
            try:
                await progress_msg.edit_text(
                    f"🛰 **ব্রডকাস্ট লাইভ প্রগ্রেস রিপোর্ট**\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"🌀 অগ্রগতি: [{progress_bar}] {percentage:.1f}%\n\n"
                    f"✅ সফল ডেলিভারি: `{sent_count}`\n"
                    f"❌ ব্যর্থ হয়েছে: `{failed_count}`\n"
                    f"🚨 Traffic Police: `{traffic_police}`\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"💡 প্রতি সেকেন্ডে ১০ জন ইউজার হ্যান্ডেল করা হচ্ছে।"
                )
            except: pass

        # আপনার রিকোয়েস্ট অনুযায়ী ব্রডকাস্টের গতি ১০/সেকেন্ড (0.1s sleep)
        # এটি ভারসাম্যপূর্ণ কারণ সেকেন্ডে বাকি ১৫টি স্পট সাধারণ ইউজারদের জন্য বরাদ্দ।
        await asyncio.sleep(0.1) 

    # --- ব্রডকাস্ট শেষ হওয়ার পর ফাইনাল লজিক ---
    duration = round(time.time() - start_time, 2)
    
    # আপনার রিকোয়েস্ট: ব্রডকাস্ট শেষে Traffic Police ২৫ হয়ে যাবে
    traffic_manager.limit = 25
    traffic_police = 25 

    await progress_msg.delete()
    
    final_report = (
        f"✅ **ব্রডকাস্ট সফলভাবে সম্পন্ন হয়েছে!**\n\n"
        f"📊 **ফাইনাল পরিসংখ্যান:**\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👥 মোট ইউজার: `{total_users}`\n"
        f"🎯 সফল: `{sent_count}`\n"
        f"⚠️ ব্যর্থ: `{failed_count}`\n"
        f"⏱ সময় লেগেছে: `{duration}s`\n"
        f"👮 Traffic Police Status: `{traffic_police}` (Updated)\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"✨ বট এখন স্বাভাবিক এবং সর্বোচ্চ গতিতে কাজ করতে প্রস্তুত।"
    )
    
    await message.answer(final_report, reply_markup=get_admin_kb())
    await state.clear()

# --- ১১. নিরাপদ মেইন রানার ---
async def main():
    try:
        print("🤖 Bot is Starting with Firebase Cloud Database...")
        # ব্যাকআপ টাস্ক শুরু
        asyncio.create_task(send_weekly_backup())
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
        
    
