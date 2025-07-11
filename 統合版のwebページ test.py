import streamlit as st
import gspread
import json
import tempfile
from datetime import datetime
from oauth2client.service_account import ServiceAccountCredentials

# === Google Sheets 認証 ===
creds_dict = st.secrets["GOOGLE_SERVICE_ACCOUNT_JSON"].to_dict()
creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")

with tempfile.NamedTemporaryFile(delete=False, mode="w", suffix=".json") as tmp:
    json.dump(creds_dict, tmp)
    tmp_path = tmp.name

scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
credentials = ServiceAccountCredentials.from_json_keyfile_name(tmp_path, scope)
client = gspread.authorize(credentials)

# === Google Sheets 接続 ===
chat_sheet = client.open_by_key("1XpB4gzlkOS72uJMADmSIuvqECM5Ud8M-KwwJbXSxJxM").worksheet("Chat")
profile_sheet = client.open_by_key("1XpB4gzlkOS72uJMADmSIuvqECM5Ud8M-KwwJbXSxJxM").worksheet("Personality")
existing_users = [row["Username"] for row in profile_sheet.get_all_records()]


# === ユーザー認証（サイドバー）===
st.sidebar.title("User Login")

if "user_name" not in st.session_state:
    st.session_state.user_name = ""

if st.session_state.user_name == "":
    st.session_state.user_name = st.sidebar.text_input("Enter your username")
    if not st.session_state.user_name:
        st.warning("Please enter your username.")
        st.stop()
else:
    st.sidebar.markdown(f"**Welcome, {st.session_state.user_name}!**")

user_name = st.session_state.user_name

page = "Chat" if user_name in existing_users else "Personality Test"

# === ユーザー専用のチャットシートを取得 or 作成 ===
spreadsheet = client.open_by_key("1XpB4gzlkOS72uJMADmSIuvqECM5Ud8M-KwwJbXSxJxM")

try:
    chat_sheet = spreadsheet.worksheet(user_name)
except gspread.exceptions.WorksheetNotFound:
    chat_sheet = spreadsheet.add_worksheet(title=user_name, rows="1000", cols="4")
    chat_sheet.append_row(["Username", "Role", "Message", "Timestamp"])  # ヘッダー


# === 質問リスト ===
questions = [
    ("I am the life of the party", "Extraversion", False),
    ("I don't talk a lot", "Extraversion", True),
    ("I sympathize with others' feelings", "Agreeableness", False),
    ("I am not interested in other people's problems", "Agreeableness", True),
    ("I get chores done right away", "Conscientiousness", False),
    ("I often forget to put things back in their proper place", "Conscientiousness", True),
    ("I am relaxed most of the time", "Emotional Stability", False),
    ("I get upset easily", "Emotional Stability", True),
    ("I have a vivid imagination", "Openness", False),
    ("I am not interested in abstract ideas", "Openness", True)
]

# === パーソナリティテスト画面 ===
if page == "Personality Test":
    st.title("Big Five Personality Test")
    responses = []

    with st.form("personality_form"):
        st.write("Rate 1 (Disagree) to 5 (Agree)")
        for q, _, _ in questions:
            responses.append(st.slider(q, 1, 5, 3))
        submitted = st.form_submit_button("Submit")

    if submitted:
        traits = {t: 0 for _, t, _ in questions}
        trait_counts = {t: 0 for t in traits}
        for r, (q, t, rev) in zip(responses, questions):
            traits[t] += 6 - r if rev else r
            trait_counts[t] += 1

        st.subheader("Your Personality Results")
        row = [user_name]
        for trait in traits:
            avg = traits[trait] / trait_counts[trait] * 20
            st.write(f"{trait}: {round(avg)} / 100")
            row.append(round(avg))

        profile_sheet.append_row(row)
        st.success("Saved. You can now proceed to chat.")
        st.session_state["completed_test"] = True

    if st.session_state.get("completed_test", False):
        if st.button("Go to Chat"):
            st.rerun()


# === Chat画面 ===
def get_profile(user):
    for row in profile_sheet.get_all_records():
        if row["Username"] == user:
            return row
    return None

def generate_persona_prompt(profile):
    if profile["Emotional Stability"] < 50:
        return "You are a calm and emotionally supportive AI."
    elif profile["Extraversion"] < 50:
        return "You are a quiet and thoughtful AI."
    elif profile["Openness"] > 70:
        return "You are a poetic and reflective AI."
    else:
        return "You are a dependable and logical AI."

def generate_response(user_input):
    persona = st.session_state.persona_prompt
    return f"{persona}\n\n(This is a placeholder reply for: '{user_input}')"

if page == "Chat":
    st.title(f"Chatbot - {user_name}")

    profile = get_profile(user_name)
    if not profile:
        st.error("No profile found. Please take the test first.")
        st.stop()

    if "persona_prompt" not in st.session_state:
        st.session_state.persona_prompt = generate_persona_prompt(profile)

    if "chat_history" not in st.session_state:
        # === 初回のみ：Google Sheets からチャット履歴をロード ===
        chat_history = []
        rows = chat_sheet.get_all_values()[1:]  # ヘッダー除外
        for row in rows:
            name, role, message, _ = row
            if name == user_name:
                chat_history.append({"role": role, "content": message})
        st.session_state.chat_history = chat_history


    for msg in st.session_state.chat_history:
        role = msg["role"].lower()
        bubble_color = "#DCF8C6" if role == "user" else "#E8E8E8"
    
        with st.chat_message(role):
            st.markdown(
                f"""
                <div style="background-color: {bubble_color}; color:black; padding: 10px; border-radius: 10px; max-width: 90%; word-wrap: break-word;">
                    {msg['content']}
                </div>
                """,
                unsafe_allow_html=True
            )


    user_input = st.chat_input("Your message")
    if user_input:
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        st.session_state.chat_history.append({"role": "User", "content": user_input})
        ai_reply = generate_response(user_input)
        st.session_state.chat_history.append({"role": "AI", "content": ai_reply})

        chat_sheet.append_row([user_name, "user", user_input, now])
        chat_sheet.append_row([user_name, "bot", ai_reply, now])
        st.rerun()


    if st.button("Clear Chat"):
        st.session_state.chat_history = []
        st.rerun()
