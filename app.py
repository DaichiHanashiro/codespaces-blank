import streamlit as st
import datetime
import pandas as pd
import requests
import qrcode
from io import BytesIO
from streamlit_calendar import calendar

st.set_page_config(layout="wide")

# ─── 1. 設定・データの読み込み ───
try:
    sheet_url = st.secrets["connections"]["gsheets"]["spreadsheet"]
    gas_url = st.secrets["connections"]["gsheets"]["gas_url"]
    csv_url = sheet_url.replace("/edit?usp=sharing", "/gviz/tq?tqx=out:csv").replace("/edit", "/gviz/tq?tqx=out:csv")
    
    df = pd.read_csv(csv_url, dtype=str)
    df = df.apply(lambda x: x.str.strip() if x.dtype == "object" else x)

    if len(df.columns) >= 3:
        if len(df.columns) == 3:
            df.columns = ["名前", "予約日", "時間帯"]
            df["パスワード"] = ""
        else:
            df = df.iloc[:, :4]
            df.columns = ["名前", "予約日", "時間帯", "パスワード"]
except Exception as e:
    st.error(f"設定ファイルまたはデータの読み込みに失敗しました: {e}")
    st.stop()


# ─── 2. URLパラメータと名前の記憶処理（端末固定強化版） ───
query_params = st.query_params
auto_action = query_params.get("action", None)
url_user = query_params.get("user", "")

# 端末（セッション）での名前保持初期化
if "saved_user" not in st.session_state:
    st.session_state["saved_user"] = ""

# URLに名前が載っていれば、最優先で端末（セッション）に記憶させる
if url_user:
    st.session_state["saved_user"] = url_user

# 端末に記憶されている名前を取得
user_name = st.session_state["saved_user"]


# ⚡⚡⚡ 3. 【QR自動打刻判定】 ───
if auto_action in ["checkin", "checkout"]:
    st.subheader("⚡ 自動打刻（入退室）")
    
    # 1️⃣ 端末に名前の記憶が一切ない場合（初回のみ）
    if not user_name:
        st.info("💡 初めての方は、お名前を入力してください。（この端末に記憶され、次回からQR読み取りだけで即打刻されます！）")
        input_name = st.text_input("お名前を入力してEnter")
        if input_name:
            clean_name = input_name.strip()
            st.session_state["saved_user"] = clean_name
            # URLに名前を付与して再読み込み
            st.query_params["action"] = auto_action
            st.query_params["user"] = clean_name
            st.rerun()
    
    # 2️⃣ 端末に名前が記憶されている場合（即座に全自動打刻！）
    else:
        if "auto_done" not in st.session_state:
            st.session_state["auto_done"] = True
            log_payload = {"action": auto_action, "name": user_name}
            try:
                res = requests.post(gas_url, json=log_payload)
                if "Success" in res.text:
                    status_label = "入室" if auto_action == "checkin" else "退室"
                    st.balloons()
                    st.success(f"🎉【{status_label}完了】{user_name} さんの打刻を記録しました！（{datetime.datetime.now().strftime('%H:%M')}）")
                else:
                    st.error(f"打刻エラー: {res.text}")
            except Exception as e:
                st.error(f"通信エラー: {e}")
        else:
            status_label = "入室" if auto_action == "checkin" else "退室"
            st.success(f"✅ {user_name} さんの【{status_label}】は打刻済みです。")
            
        st.divider()


st.title("スタジオ総合管理システム 🛡️📱")

tab1, tab2, tab3 = st.tabs(["📅 予約＆カレンダー", "🚪 ワンタップ打刻", "🔲 壁貼り用QR作成"])

# ─── タブ1：予約＆カレンダー画面 ───
with tab1:
    calendar_events = []
    if not df.empty:
        for index, row in df.iterrows():
            try:
                time_slot_str = str(row["時間帯"])
                date_str = str(row["予約日"])
                name_str = str(row["名前"])

                if "-" in time_slot_str:
                    time_range = time_slot_str.split("-")
                    start_time = time_range[0].strip()
                    end_time = time_range[1].strip()
                    
                    if len(start_time.split(":")[0]) == 1:
                        start_time = "0" + start_time
                    if len(end_time.split(":")[0]) == 1:
                        end_time = "0" + end_time
                    
                    calendar_events.append({
                        "title": f"{name_str} ({time_slot_str})",
                        "start": f"{date_str}T{start_time}:00",
                        "end": f"{date_str}T{end_time}:00",
                        "backgroundColor": "#3498db",
                        "borderColor": "#2980b9"
                    })
            except Exception:
                continue

    col1, col2 = st.columns([1, 2])

    with col1:
        st.subheader("📝 新規予約")
        date = st.date_input("予約日", datetime.date.today())
        
        col_start, col_end = st.columns(2)
        with col_start:
            start_time_input = st.time_input("開始時刻", datetime.time(9, 0))
        with col_end:
            end_time_input = st.time_input("終了時刻", datetime.time(10, 0))

        time_slot = f"{start_time_input.strftime('%H:%M')}-{end_time_input.strftime('%H:%M')}"

        with st.form("reserve_form"):
            name = st.text_input("お名前", value=user_name if user_name else "")
            password = st.text_input("キャンセル用暗証番号（4桁など）", type="password")
            submit = st.form_submit_button("予約する")

        if submit:
            if start_time_input >= end_time_input:
                st.error("終了時刻は開始時刻より後の時間に設定してください。")
            elif not name:
                st.error("名前を入力してください。")
            elif not password:
                st.error("暗証番号を入力してください。")
            else:
                is_overlap = False
                overlap_info = ""
                
                if not df.empty and "予約日" in df.columns:
                    target_date_df = df[df["予約日"] == str(date)]
                    
                    for idx, row in target_date_df.iterrows():
                        try:
                            exist_start_str, exist_end_str = row["時間帯"].split("-")
                            exist_start = datetime.datetime.strptime(exist_start_str.strip(), "%H:%M").time()
                            exist_end = datetime.datetime.strptime(exist_end_str.strip(), "%H:%M").time()
                            
                            if (start_time_input < exist_end) and (end_time_input > exist_start):
                                is_overlap = True
                                overlap_info = f"{row['名前']} さんの予約 ({row['時間帯']})"
                                break
                        except Exception:
                            continue
                
                if is_overlap:
                    st.error(f"❌ 選択した時間帯は既に予約が入っています！\n重複: {overlap_info}")
                else:
                    payload = {
                        "name": name, 
                        "date": str(date), 
                        "time_slot": time_slot,
                        "password": str(password)
                    }
                    try:
                        response = requests.post(gas_url, json=payload)
                        if response.text == "Success":
                            st.success(f"🎉 {name}さんの予約完了！（{time_slot}）")
                            st.rerun()
                        else:
                            st.error(f"書き込み失敗: {response.text}")
                    except Exception as e:
                        st.error(f"通信エラー: {e}")

        st.divider()

        st.subheader("❌ 予約のキャンセル")
        if not df.empty:
            cancel_options = [f"{row['名前']} さんの予約 ({row['予約日']} : {row['時間帯']})" for index, row in df.iterrows()]
            
            with st.form("cancel_form"):
                selected_cancel = st.selectbox("キャンセルする予定", cancel_options)
                input_password = st.text_input("予約時の暗証番号", type="password")
                cancel_submit = st.form_submit_button("この予約をキャンセル")
                
            if cancel_submit:
                if not input_password:
                    st.error("暗証番号を入力してください。")
                else:
                    opt_index = cancel_options.index(selected_cancel)
                    target_row = df.iloc[opt_index]
                    
                    cancel_payload = {
                        "action": "cancel",
                        "name": str(target_row["名前"]),
                        "date": str(target_row["予約日"]),
                        "time_slot": str(target_row["時間帯"]),
                        "password": str(input_password)
                    }
                    
                    try:
                        response = requests.post(gas_url, json=cancel_payload)
                        if response.text == "Success_Cancel":
                            st.success("❌ 予約をキャンセルしました！")
                            st.rerun()
                        else:
                            st.error(f"失敗: {response.text}")
                    except Exception as e:
                        st.error(f"通信エラー: {e}")
        else:
            st.info("現在、キャンセルできる予約はありません。")

    with col2:
        st.subheader("📅 予約カレンダー")
        
        calendar_css = """
            .fc-header-toolbar {
                display: flex !important;
                flex-wrap: wrap !important;
                gap: 4px !important;
                justify-content: space-between !important;
            }
            .fc-toolbar-title {
                font-size: 0.95rem !important;
                white-space: normal !important;
                line-height: 1.2 !important;
            }
            .fc-button {
                padding: 0.2em 0.4em !important;
                font-size: 0.75rem !important;
            }
            .fc-col-header-cell-cushion {
                font-size: 0.7rem !important;
                padding: 2px 0 !important;
                display: block !important;
                text-align: center !important;
            }
            .fc-timegrid-slot-label-cushion {
                font-size: 0.7rem !important;
                padding: 0 2px !important;
            }
        """

        calendar_options = {
            "initialView": "timeGridWeek",
            "headerToolbar": {
                "left": "prev,next today",
                "center": "title",
                "right": "timeGridWeek,timeGridDay,dayGridMonth"
            },
            "locale": "ja",
            "slotMinTime": "00:00:00",
            "slotMaxTime": "24:00:00",
            "allDaySlot": False,
            "titleFormat": { "year": "numeric", "month": "short", "day": "numeric" },
            "buttonText": {
                "today": "今日",
                "month": "月",
                "week": "週",
                "day": "日"
            }
        }
        
        calendar(events=calendar_events, options=calendar_options, custom_css=calendar_css)

# ─── タブ2：ワンタップ手動打刻（画面からの手動打刻用） ───
with tab2:
    st.subheader("📱 入退室打刻（手動）")
    
    if user_name:
        st.success(f"👤 **{user_name}** さんとして認識されています")
    else:
        st.info("💡 お名前を入力して登録すると、この端末に自動記憶されます。")
        input_name = st.text_input("お名前を入力")
        if input_name:
            user_name = input_name.strip()
            st.session_state["saved_user"] = user_name
            st.query_params["user"] = user_name
            st.rerun()

    st.divider()

    col_in, col_out = st.columns(2)
    with col_in:
        if st.button("🚪 入室（打刻）", use_container_width=True, type="primary"):
            if user_name:
                log_payload = {"action": "checkin", "name": user_name}
                try:
                    res = requests.post(gas_url, json=log_payload)
                    if "Success" in res.text:
                        st.balloons()
                        st.success(f"✅ {user_name} さん、入室を記録しました！")
                    else:
                        st.error(f"打刻エラー: {res.text}")
                except Exception as e:
                    st.error(f"通信エラー: {e}")
            else:
                st.warning("お名前を入力してください。")

    with col_out:
        if st.button("🚪 退室（打刻）", use_container_width=True):
            if user_name:
                log_payload = {"action": "checkout", "name": user_name}
                try:
                    res = requests.post(gas_url, json=log_payload)
                    if "Success" in res.text:
                        st.success(f"👋 {user_name} さん、退室を記録しました！")
                    else:
                        st.error(f"打刻エラー: {res.text}")
                except Exception as e:
                    st.error(f"通信エラー: {e}")
            else:
                st.warning("お名前を入力してください。")

# ─── タブ3：🔲 自動打刻用QRコード生成 ───
with tab3:
    st.subheader("🔲 壁貼り用 自動打刻QRコード作成")
    st.write("部屋の入り口（入室用）と出口（退室用）に貼るQRコードを作成できます。")
    
    # 既存のアプリURLをデフォルトでセット
    base_url = st.text_input("アプリのベースURL", value="https://mmc-studio.streamlit.app")
    
    col_qr1, col_qr2 = st.columns(2)
    
    with col_qr1:
        st.markdown("### 🚪 入室専用QR")
        if st.button("入室用QRを作成"):
            qr_url = f"{base_url}?action=checkin"
            qr = qrcode.QRCode(version=1, box_size=8, border=4)
            qr.add_data(qr_url)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            
            buf = BytesIO()
            img.save(buf, format="PNG")
            byte_im = buf.getvalue()
            
            st.image(byte_im, caption="入室用QR", width=200)
            st.download_button("📥 入室QRをダウンロード", data=byte_im, file_name="checkin_qr.png", mime="image/png")

    with col_qr2:
        st.markdown("### 🚪 退室専用QR")
        if st.button("退室用QRを作成"):
            qr_url = f"{base_url}?action=checkout"
            qr = qrcode.QRCode(version=1, box_size=8, border=4)
            qr.add_data(qr_url)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            
            buf = BytesIO()
            img.save(buf, format="PNG")
            byte_im = buf.getvalue()
            
            st.image(byte_im, caption="退室用QR", width=200)
            st.download_button("📥 退室QRをダウンロード", data=byte_im, file_name="checkout_qr.png", mime="image/png")