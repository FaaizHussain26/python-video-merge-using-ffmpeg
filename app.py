from flask import Flask, request, jsonify
from dotenv import load_dotenv
from  video_merger import VideoDriveMerger

import os

load_dotenv()
app = Flask(__name__)

@app.route("/merge_videos", methods=["POST"])
def merge_videos():
    try:
        data = request.get_json()
        video1_link = data.get("video1_link")
        output_folder_id = data.get("output_folder_id")

        if not video1_link :
            return jsonify({"error": "Both video links are required"}), 400
        
        video2_link="https://drive.google.com/file/d/1ixRG79dLW7seMRrOVJybgMkSavZrdi7G/view?usp=sharing"
        merger = VideoDriveMerger()
        result = merger.process(video1_link,video2_link, output_folder_id)

        return jsonify({
            "message": "Merge successful!",
            "file_id": result.get("id"),
            "webViewLink": result.get("webViewLink")
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    print(f"🚀 Running API on http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=True)
