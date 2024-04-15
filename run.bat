call ./venv/Scripts/activate

pip install -r requirements.txt

streamlit run .\webui\Main.py --browser.gatherUsageStats=False --server.enableCORS=True
