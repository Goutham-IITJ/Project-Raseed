# Project Raseed 🧾✨

**Project Raseed** is a next-generation financial assistant designed to bridge the gap between physical receipts and digital financial health. Built for the **Google Cloud Agentic AI Day**, it uses **Gemini 2.5 Flash** to autonomously ingest, categorize, and reason about your spending, while integrating directly with **Google Wallet**.

## 🚀 Key Features

- **📷 Visual Ingestion (Gemini Vision):** Instantly extracts merchant details, line items, taxes, and **spending categories** (e.g., Dining, Groceries) from receipt images.
- **💳 Google Wallet Integration:** "Mint" your physical receipts into dynamic **Google Wallet Passes** with a single click. Uses signed JWTs for secure pass creation.
- **🧠 Agentic AI Assistant:** A LangChain SQL Agent (powered by Gemini) that you can chat with. Ask questions like _"How much did I spend on coffee?"_ or _"Do I have any shampoo left?"_.
- **📊 Smart Analytics:** Interactive dashboard showing spending breakdowns by category using Plotly charts.
- **💾 Local & Secure:** Uses a robust local SQLite database with self-healing schema architecture.

## 🛠️ Technology Stack

- **AI Model:** Google Gemini 1.5 Flash (via `google-generativeai`)
- **Frontend:** Streamlit (Python)
- **Orchestration:** LangChain (SQL Database Toolkit)
- **Database:** SQLite (Simulating Firebase Firestore)
- **Mobile Wallet:** Google Wallet API (REST & JWT)
- **Visualization:** Plotly Express

## ⚙️ Installation & Setup

1.  **Clone the repository:**

    ```bash
    git clone [https://github.com/Goutham-IITJ/Project-Raseed.git](https://github.com/Goutham-IITJ/Project-Raseed.git)
    cd Project-Raseed
    ```

2.  **Install dependencies:**

    ```bash
    pip install -r requirements.txt
    ```

3.  **Set up Credentials:**

    - Create a `.env` file in the root directory.
    - Add your Google Cloud API Key:
      ```
      GOOGLE_API_KEY=your_gemini_api_key_here
      ```
    - **For Wallet Features:** Place your Service Account JSON key in the root folder and name it `wallet_key.json`.

4.  **Run the App:**
    ```bash
    streamlit run main.py
    ```

## 📂 Project Structure

Project-Raseed/ ├── main.py # Entry point & Navigation ├── requirements.txt # Python Dependencies ├── images/ # Assets (Logos, Icons) ├── uploaded_invoices/ # Local storage for receipts ├── utilities/ │ ├── ocr_gptvision.py # Gemini Vision Extractor │ ├── wallet_helper.py # Google Wallet JWT Engine │ └── home.py # Home Page UI ├── database_files/ │ └── sqlite_db.py # Database Manager (CRUD) └── navigation_pages/ ├── ai_chat.py # Raseed Agent (Chatbot) ├── invoice_history.py # Analytics & Wallet Actions └── ...

## 👨‍💻 Developer

**Goutham A.S**

- _Sole Developer & Architect_
- Focus: Agentic AI, Full Stack Python, Cloud Integration

## 📄 License

This project is licensed under the MIT License.
