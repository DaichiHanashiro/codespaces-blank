import streamlit as st
from datetime import datetime, timezone, timedelta, date, time
import pandas as pd
import requests
import qrcode
from io import BytesIO
from streamlit_calendar import calendar

st.set_page_config(layout="wide", page_title="スタジオ管理システム", page_icon="🚪")

# 🇯🇵 日本標準時（JST = UTC+9）の定義
JST = timezone(timedelta(hours=9))

# ─── 1. 設定・データの読み込み ───
try:
    sheet_url = st.secrets["connections"]["gsheets"]["spreadsheet"]
    gas_url = st.secrets["connections"]["gsheets"]["gas_url"]
    csv_url = sheet_url.replace("/edit?usp=sharing", "/gviz/tq?tqx=out:csv").replace("/edit", "/gviz/tq?tqx=out:csv")
    
    df = pd.read_csv(csv_url, dtype=str)
    df = df.apply(lambda x: x.str.strip() if x.dtype == "object" else x)

    if len(df.columns) >= 3:
        if len(df.columns) == 3:
            df.columns = ["名前", "予約日", "時間"]
            df["パスワード"] = ""
        else:
            df = df.iloc[:, :4]
            df.columns = ["名前", "予約日", "時間", "パスワード"]
except Exception as e:
    st.error(f"設定ファイルまたはデータの読み込みに失敗しました: {e}")
    st.stop()

# URLパラメータ取得
query_params = st.query_params
is_admin = query_params.get("admin", None) == "true"  # 🤫 ?admin=true で管理者モード


st.title("MMCスタジオ管理システム")

# 🤫 管理者フラグ(is_admin)がTrueの時だけ3つ目のタブを表示！
if is_admin:
    tab1, tab2, tab3 = st.tabs(["🚪 打刻（入室・退室）", "📅 予約＆カレンダー", "🔲 壁貼り用QR作成（管理者）"])
else:
    tab1, tab2 = st.tabs(["🚪 打刻（入室・退室）", "📅 予約＆カレンダー"])


# ─── タブ1：打刻画面（メイン） ───
with tab1:
    st.subheader("📱 入退室打刻")
    st.write("名前を入力して、入室または退室ボタンを押してください。")

    # オートフィル対応のテキスト入力欄
    user_name_input = st.text_input("名前", key="main_user_name")
    
    st.divider()

    col_in, col_out = st.columns(2)
    
    with col_in:
        if st.button("🚪 入室する", use_container_width=True, type="primary"):
            if user_name_input:
                # 🇯🇵 日本時間の現在時刻を取得
                now_jst = datetime.now(JST)
                time_str = now_jst.strftime('%H:%M')

                log_payload = {
                    "action": "checkin", 
                    "name": user_name_input.strip(),
                    "time": time_str
                }
                try:
                    res = requests.post(gas_url, json=log_payload)
                    if "Success" in res.text:
                        st.balloons()
                        st.success(f"🎉 **{user_name_input}** さん、入室を記録しました！（{time_str}）")
                    else:
                        st.error(f"打刻エラー: {res.text}")
                except Exception as e:
                    st.error(f"通信エラー: {e}")
            else:
                st.warning("⚠️ 名前を入力してください。")

    with col_out:
        if st.button("🚪 退室する", use_container_width=True):
            if user_name_input:
                # 🇯🇵 日本時間の現在時刻を取得
                now_jst = datetime.now(JST)
                time_str = now_jst.strftime('%H:%M')

                log_payload = {
                    "action": "checkout", 
                    "name": user_name_input.strip(),
                    "time": time_str
                }
                try:
                    res = requests.post(gas_url, json=log_payload)
                    if "Success" in res.text:
                        st.success(f"👋 **{user_name_input}** さん、退室を記録しました！（{time_str}）")
                    else:
                        st.error(f"打刻エラー: {res.text}")
                except Exception as e:
                    st.error(f"通信エラー: {e}")
            else:
                st.warning("⚠️ 名前を入力してください。")


# ─── タブ2：予約＆カレンダー画面 ───
with tab2:
    calendar_events = []
    if not df.empty:
        for index, row in df.iterrows():
            try:
                time_slot_str = str(row["時間"])
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
        # 🇯🇵 予約日選択の初期値を日本時間の「今日」に設定
        today_jst = datetime.now(JST).date()
        date_val = st.date_input("予約日", today_jst)
        
        col_start, col_end = st.columns(2)
        with col_start:
            start_time_input = st.time_input("開始時刻", time(9, 0))
        with col_end:
            end_time_input = st.time_input("終了時刻", time(10, 0))

        time_slot = f"{start_time_input.strftime('%H:%M')}-{end_time_input.strftime('%H:%M')}"

        with st.form("reserve_form"):
            name = st.text_input("名前")
            password = st.text_input("キャンセル用パスワード", type="password")
            submit = st.form_submit_button("予約する")

        if submit:
            if start_time_input >= end_time_input:
                st.error("終了時刻は開始時刻より後の時間に設定してください。")
            elif not name:
                st.error("名前を入力してください。")
            elif not password:
                st.error("パスワードを入力してください。")
            else:
                is_overlap = False
                overlap_info = ""
                
                if not df.empty and "予約日" in df.columns:
                    target_date_df = df[df["予約日"] == str(date_val)]
                    
                    for idx, row in target_date_df.iterrows():
                        try:
                            exist_start_str, exist_end_str = row["時間"].split("-")
                            exist_start = datetime.strptime(exist_start_str.strip(), "%H:%M").time()
                            exist_end = datetime.strptime(exist_end_str.strip(), "%H:%M").time()
                            
                            if (start_time_input < exist_end) and (end_time_input > exist_start):
                                is_overlap = True
                                overlap_info = f"{row['名前']} さんの予約 ({row['時間']})"
                                break
                        except Exception:
                            continue
                
                if is_overlap:
                    st.error(f"❌ 選択した時間は既に予約が入っています！\n重複: {overlap_info}")
                else:
                    payload = {
                        "name": name, 
                        "date": str(date_val), 
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
            cancel_options = [f"{row['名前']} さんの予約 ({row['予約日']} : {row['時間']})" for index, row in df.iterrows()]
            
            with st.form("cancel_form"):
                selected_cancel = st.selectbox("キャンセルする予約", cancel_options)
                input_password = st.text_input("キャンセル用パスワード", type="password")
                cancel_submit = st.form_submit_button("この予約をキャンセル")
                
            if cancel_submit:
                if not input_password:
                    st.error("パスワードを入力してください。")
                else:
                    opt_index = cancel_options.index(selected_cancel)
                    target_row = df.iloc[opt_index]
                    
                    cancel_payload = {
                        "action": "cancel",
                        "name": str(target_row["名前"]),
                        "date": str(target_row["予約日"]),
                        "time_slot": str(target_row["時間"]),
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
            "height": 800,  # ↕️ 縦幅をガッツリ伸ばして夜の時間帯まで見やすく！
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


# ─── タブ3：🔲 自動打刻用QRコード生成（管理者専用） ───
if is_admin:
    with tab3:
        st.subheader("🔲 壁貼り用 打刻QRコード作成（共通1枚）")
        st.write("スタジオの壁に貼る打刻用の共通QRコードを作成します。")
        
        base_url = st.text_input("アプリのベースURL", value="https://mmc-studio.streamlit.app")
        
        if st.button("壁貼り用QRコードを作成"):
            qr = qrcode.QRCode(version=1, box_size=8, border=4)
            qr.add_data(base_url)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            
            buf = BytesIO()
            img.save(buf, format="PNG")
            byte_im = buf.getvalue()
            
            st.image(byte_im, caption="スタジオ打刻用QR（共通）", width=220)
            st.download_button("📥 QRコードをダウンロード", data=byte_im, file_name="studio_checkin_qr.png", mime="image/png")