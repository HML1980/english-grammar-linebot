from flask import Flask, request, jsonify
import config

# 建立Flask應用程式
app = Flask(__name__)

@app.route("/", methods=['GET'])
def index():
    """首頁，顯示BOT狀態"""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>英文文法攻略 LINE BOT</title>
        <meta charset="UTF-8">
        <style>
            body { font-family: Arial, sans-serif; margin: 40px; background: #f5f5f5; }
            .container { background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
            h1 { color: #333; }
            .status { color: #28a745; font-weight: bold; }
            .info { margin: 10px 0; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🎯 英文文法攻略 LINE BOT</h1>
            <div class="info">BOT狀態: <span class="status">正常運行中 ✅</span></div>
            <div class="info">版本: 1.0.0</div>
            <div class="info">開發階段: 第一階段 - 基礎環境設定</div>
            <div class="info">框架: Flask 3.1.1</div>
            <div class="info">Python: 3.12.1</div>
        </div>
    </body>
    </html>
    """

@app.route("/health", methods=['GET'])
def health_check():
    """健康檢查端點"""
    return jsonify({
        "status": "healthy",
        "version": "1.0.0",
        "message": "英文文法攻略 LINE BOT 運行正常"
    })

@app.route("/callback", methods=['POST'])
def callback():
    """LINE BOT Webhook回調函數（暫時版本）"""
    return jsonify({
        "message": "Webhook 已設定，等待 LINE BOT 設定完成"
    })

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000, debug=config.FLASK_DEBUG)