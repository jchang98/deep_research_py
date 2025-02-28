import streamlit as st
import subprocess
from run import *
import asyncio
from datetime import datetime

st.set_page_config(layout="wide")
st.title('📖 Hithink Deep Research V2')

def clean():
    # 保持用户输入为空
    st.session_state['user_input'] = []
    st.session_state['input_type'] = ""
    st.session_state["follow_up_questions"] = []
    st.session_state["start_time"] = ""
    
    # 使用rerun来刷新整个页面
    st.rerun()



    
def main():
    if 'user_input' not in st.session_state:
        st.session_state['user_input'] = []
    if 'input_type' not in st.session_state:
        st.session_state['input_type'] = ""
    if "follow_up_questions" not in st.session_state:
        st.session_state["follow_up_questions"] = []
    if "start_time" not in st.session_state:
        st.session_state["start_time"] = ""

    model = st.sidebar.selectbox('选择模型', ['gpt-4o-mini', 'gpt-4o', 'deepseek-r1'])
    breadth = st.sidebar.slider('选择宽度', min_value=2, max_value=10, value=5)
    depth = st.sidebar.slider('选择深度', min_value=1, max_value=5, value=5)
    max_followup_questions = st.sidebar.slider('最大澄清问题数', min_value=1, max_value=5, value=5)
    clear = st.sidebar.button("clear")
    if clear:
        clean()

    user_input = st.chat_input("Enter a question:")


    if user_input and st.session_state['input_type'] == "":
        # 第一次输入
        start_time = datetime.now()
        follow_up_questions = asyncio.run(get_feedback(concurrency=5, service="", max_followup_questions=max_followup_questions, enable_logging=True, log_path="logs", log_to_stdout=False, query=user_input, model=model, depth=depth, breadth=breadth, start_time=start_time))

        st.session_state['input_type'] = "feedback"
        st.session_state['user_input'].append(user_input)
        st.session_state['follow_up_questions'] = follow_up_questions
        st.session_state['start_time'] = start_time


    elif user_input and st.session_state['input_type'] == "feedback":
        follow_up_answers = [user_input]
        user_input_orig = st.session_state['user_input'][0]
        follow_up_questions = st.session_state['follow_up_questions']
        start_time = st.session_state['start_time']

        asyncio.run(answer_main(concurrency=5, service="", max_followup_questions=max_followup_questions, enable_logging=True, log_path="logs", log_to_stdout=False, query=user_input_orig, model=model, depth=depth, breadth=breadth, start_time=start_time, follow_up_questions=follow_up_questions, answers=follow_up_answers))
        st.session_state['input_type'] = ""
                  


if __name__ == '__main__':
    main()
