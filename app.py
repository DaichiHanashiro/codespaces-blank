import streamlit as st
from datetime import datetime, timezone, timedelta, date, time
import pandas as pd
import requests
import qrcode
from io import BytesIO
from streamlit_calendar import calendar

st.set_page_config(layout="wide", page_title="スタジオ管理システム", page_icon="🚪")

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
    st.error(f"データの読み込みに失敗しました: {e}")
    st.stop()

query_params = st.query_params
is_admin = query_params.get("admin", None) == "true"

st.title("MMCスタジオ管理システムtest")

if is_admin:
    tab1, tab2, tab3 = st.tabs(["🚪 打刻", "📅 予約", "🔲 管理"])
else:
    tab1, tab2 = st.tabs(["🚪 打刻", "📅 予約"])

# ─── タブ1：打刻 ───
with tab1:
    st.subheader("📱 入退室打刻")
    user_name_input = st.text_input("名前", key="main_user_name")
    col_in, col_out = st.columns(2)
    
    with col_in:
        if st.button("🚪 入室", use_container_width=True, type="primary"):
            if user_name_input:
                now_jst = datetime.now(JST).strftime('%H:%M')
                res = requests.post(gas_url, json={"action": "checkin", "name": user_name_input.strip(), "time": now_jst})
                if "Success" in res.text:
                    st.success(f"入室しました！({now_jst})")
    with col_out:
        if st.button("🚪 退室", use_container_width=True):
            if user_name_input:
                now_jst = datetime.now(JST).strftime('%H:%M')
                res = requests.post(gas_url, json={"action": "checkout", "name": user_name_input.strip(), "time": now_jst})
                if "Success" in res.text:
                    st.success(f"退室しました！({now_jst})")

# ─── タブ2：予約 ───
with tab2:
    col1, col2 = st.columns([1, 2])
    with col1:
        st.subheader("📝 新規予約")
        date_val = st.date_input("予約日", datetime.now(JST).date(), key="res_date")
        
        # 💡 3ステップ・ボタン選択
        st.write("① **開始時**")
        start_hour = st.pills("時", [f"{h:02d}時" for h in range(8, 24)], selection_mode="single", default="09時")
        
        st.write("② **開始分**")
        start_min = st.pills("分", ["00分", "15分", "30分", "45分"], selection_mode="single", default="00分")
        
        st.write("③ **利用時間**")
        dur_dict = {"30分": 30, "1時間": 60, "1.5時間": 90, "2時間": 120, "3時間": 180}
        selected_dur = st.pills("時間", list(dur_dict.keys()), selection_mode="single", default="1時間")
        
        # 予約時間の計算
        h = int(start_hour.replace("時", ""))
        m = int(start_min.replace("分", ""))
        start_dt = datetime(2026, 1, 1, h, m)
        end_dt = start_dt + timedelta(minutes=dur_dict[selected_dur])
        
        start_time_str = start_dt.strftime("%H:%M")
        end_time_str = "24:00" if end_dt.hour == 0 and end_dt.minute == 0 else end_dt.strftime("%H:%M")
        
        st.info(f"予約枠: **{start_time_str} 〜 {end_time_str}**")
        time_slot = f"{start_time_str}-{end_time_str}"

        # 予約フォーム
        with st.form("reserve_form"):
            name = st.text_input("名前")
            password = st.text_input("キャンセル用パスワード", type="password")
            submit = st.form_submit_button("予約する", use_container_width=True)

        if submit:
            if not name or not password:
                st.error("名前とパスワードを入力してください。")
            else:
                payload = {"name": name, "date": str(date_val), "time_slot": time_slot, "password": password}
                res = requests.post(gas_url, json=payload)
                if res.text == "Success":
                    st.success("予約完了！")
                    st.rerun()
                else:
                    st.error(f"エラー: {res.text}")

        # 🔍 キャンセル機能（検索フィルター付き）
        st.subheader("❌ 予約のキャンセル")
        if not df.empty:
            search_name = st.text_input("🔍 名前で予約を検索（部分一致）", placeholder="名前を入力して絞り込み...")

            filtered_df = df.copy()
            if search_name:
                filtered_df = filtered_df[filtered_df["名前"].str.contains(search_name.strip(), na=False)]

            if not filtered_df.empty:
                cancel_options = [f"{row['名前']} さんの予約 ({row['予約日']} : {row['時間']})" for index, row in filtered_df.iterrows()]
                
                with st.form("cancel_form"):
                    selected_cancel = st.selectbox("キャンセルする予約を選択", cancel_options)
                    input_password = st.text_input("キャンセル用パスワード", type="password")
                    cancel_submit = st.form_submit_button("この予約をキャンセル", use_container_width=True)
                    
                if cancel_submit:
                    if not input_password:
                        st.error("パスワードを入力してください。")
                    else:
                        opt_index = cancel_options.index(selected_cancel)
                        target_row = filtered_df.iloc[opt_index]
                        
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
                st.info(f"「{search_name}」さんの予約は見つかりませんでした。")
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
            "height": 800,
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