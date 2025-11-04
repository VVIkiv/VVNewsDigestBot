import asyncio
import os
from telethon import TelegramClient
from telethon.sessions import StringSession
from config import API_ID, API_HASH

async def main():
    print("⚙️  Environment: LOCAL (auto-detected)")
    print("📁 Current directory:", os.getcwd())
    print("📄 .env exists:", os.path.exists(".env"))
    print("🔍 Render detected:", "/opt/render" in os.getcwd())

    # Генерація StringSession для деплою (Render)
    client = TelegramClient(StringSession(), API_ID, API_HASH)
    await client.connect()

    # QR-логін без телефонного коду
    print("\n📱 Відкрийте Telegram → Налаштування → Пристрої → Прив'язати пристрій Desktop і скануйте QR нижче або відкрийте посилання.")
    try:
        import qrcode
        use_ascii_qr = True
    except Exception:
        qrcode = None
        use_ascii_qr = False

    qr = await client.qr_login()
    if qr is not None and getattr(qr, 'url', None):
        while True:
            # Відображення QR
            print("\nПосилання для прив'язки (можна відкрити на телефоні):")
            print(qr.url)
            # Вивід ASCII QR (за наявності) та збереження PNG для сканування
            if use_ascii_qr and qrcode is not None:
                try:
                    qr_img = qrcode.QRCode(border=1)
                    qr_img.add_data(qr.url)
                    qr_img.make(fit=True)
                    qr_img.print_ascii(invert=True)
                    try:
                        img = qr_img.make_image(fill_color="black", back_color="white")
                        img_path = os.path.abspath("telethon_qr.png")
                        img.save(img_path)
                        print(f"📷 Збережено QR як файл: {img_path}")
                        try:
                            if os.name == 'nt':
                                os.startfile(img_path)
                        except Exception:
                            pass
                    except Exception:
                        pass
                except Exception:
                    pass
            elif qrcode is not None:
                try:
                    img = qrcode.make(qr.url)
                    img_path = os.path.abspath("telethon_qr.png")
                    img.save(img_path)
                    print(f"📷 Збережено QR як файл: {img_path}")
                    try:
                        if os.name == 'nt':
                            os.startfile(img_path)
                    except Exception:
                        pass
                except Exception:
                    pass
            print("\nОчікую підтвердження у Telegram… (QR діє ~1 хв., якщо сплив — я оновлю)")
            try:
                await qr.wait()
                break
            except Exception:
                # Якщо термін дії сплив — відновлюємо QR
                qr = await qr.recreate()
                if qr is None or not getattr(qr, 'url', None):
                    break
                continue
        print("\n✅ Успішна авторизація через QR!")
    else:
        # Фолбек: код у додатку Telegram (чат «Telegram»), без SMS
        print("\nℹ️ Ваш клієнт не підтримує QR-посилання. Переходимо до входу за кодом з чату Telegram.")
        phone = input("Введіть телефон у форматі +380...: ").strip()
        await client.send_code_request(phone)
        print("📨 Код відправлено у чат ‘Telegram’ вашого застосунку.")
        code = input("Введіть код з Telegram (не SMS): ").strip()
        try:
            await client.sign_in(phone=phone, code=code)
        except Exception as e:
            print(f"❌ Помилка входу: {e}")
            await client.disconnect()
            return
        print("\n✅ Успішна авторизація за кодом!")


    me = await client.get_me()
    if me:
        print(f"👤 Авторизовано як: {me.first_name} ({me.username or 'без username'})")
    else:
        print("⚠️ Не вдалося отримати інформацію про користувача")

    # Виводимо StringSession для використання як TELETHON_SESSION у середовищі
    try:
        session_str = client.session.save()
        if session_str:
            print("\n=== TELETHON STRING SESSION ===")
            print(session_str)
            print("=== END STRING SESSION ===\n")
            # Опціонально: зберегти у .env, якщо файл існує
            if os.path.exists('.env'):
                with open('.env', 'a', encoding='utf-8') as f:
                    f.write(f"\nTELETHON_SESSION={session_str}\n")
                print("📝 Додано TELETHON_SESSION до .env")
        else:
            print("⚠️ Не вдалося зберегти StringSession")
    finally:
        await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())