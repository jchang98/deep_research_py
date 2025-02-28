import streamlit as st

# 初始化会话状态
if 'messages' not in st.session_state:
    st.session_state.messages = []

def chat_input_reusable():
    user_input = st.chat_input("输入您的消息:")
    if user_input:
        st.session_state.messages.append(user_input)

# 使用复用的 chat_input
if __name__ == "__main__":
    st.title("Chat Application")

    # 调用复用的 chat_input
    chat_input_reusable()

    # 显示所有消息
    if st.session_state.messages:
        st.write("聊天记录:")
        for message in st.session_state.messages:
            st.write(message)
