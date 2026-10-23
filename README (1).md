# Smart Home Energy Saver

Author: Manan Mli
Project: Home Energy Optimizer – Agentic AI

This project is a Smart Home Energy Saving application designed to optimize energy consumption in smart homes. It is built using a combination of machine learning models and generative AI, leveraging a multi-agent framework (Microsoft Agent Framework). This real-time industry project predicts energy usage and provides actionable insights to save energy.

<img width="1300" height="594" alt="image" src="https://github.com/user-attachments/assets/d7e16fd9-7d0a-470d-b784-11dc9d90469e" />


## Setup Instructions

### 1. Create a Virtual Environment

#### For Windows:
```cmd
python -m venv venv
venv\Scripts\activate
```

#### For macOS/Linux:
```bash
python3 -m venv venv
source venv/bin/activate
```

### 2. Install Dependencies
Once the virtual environment is activated, install the required dependencies:
```bash
pip install -r requirements.txt
```

### 3. Configure Environment Variables
Copy `.env.example` to `.env` in the project root and fill in your Microsoft Foundry project settings and email account:

```dotenv
AZURE_OPENAI_ENDPOINT=https://your-foundry-project.services.ai.azure.com
AZURE_OPENAI_CHAT_COMPLETION_MODEL=your-model-deployment
EMAIL_SENDER=your-email@example.com
EMAIL_PASSWORD=your-gmail-app-password
```

The `.env` file is ignored by Git and must never be committed. Sign in with Azure CLI using `az login` before running the agent. To generate a Gmail app password, follow:
[Generate Email Password/Token](https://myaccount.google.com/apppasswords)

### 4. Start the Applications

To start the UI application, run the following command in one terminal:
```cmd
python app.py
```

To start the Streamlit application, run the following command in another terminal:
```cmd
streamlit run streamlit_app.py
```

---

Kaggle Dataset: https://www.kaggle.com/datasets/mexwell/smart-home-energy-consumption

Once all the steps are completed, you can run the application and start optimizing your smart home energy usage!
