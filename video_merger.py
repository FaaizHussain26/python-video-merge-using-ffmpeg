import os
import pickle
import tempfile
import shutil
import base64
import ffmpeg
import imageio_ffmpeg
import subprocess
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload

SCOPES = ['https://www.googleapis.com/auth/drive']


class VideoDriveMerger:
    def __init__(self):
        self.service = None
        self.temp_dir = tempfile.mkdtemp()

        # ✅ Use ffmpeg binary bundled with imageio-ffmpeg (no system install needed)
        self.ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()

        # Verify ffmpeg exists
        if not os.path.exists(self.ffmpeg_path):
            raise RuntimeError("FFmpeg binary not found. Try reinstalling imageio-ffmpeg.")

        # Add to PATH so subprocesses can find it
        os.environ["PATH"] += os.pathsep + os.path.dirname(self.ffmpeg_path)

        # Optional: verify ffmpeg works
        try:
            subprocess.run([self.ffmpeg_path, "-version"], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except Exception as e:
            raise RuntimeError(f"FFmpeg is not working properly: {e}")

        # Write credentials.json and token.pickle if provided via env vars
        if os.getenv("GOOGLE_CREDENTIALS_JSON"):
            with open("credentials.json", "w") as f:
                f.write(os.getenv("GOOGLE_CREDENTIALS_JSON"))

        if os.getenv("TOKEN_PICKLE_BASE64"):
            with open("token.pickle", "wb") as f:
                f.write(base64.b64decode(os.getenv("TOKEN_PICKLE_BASE64")))

    def authenticate(self):
        creds = None
        if os.path.exists('token.pickle'):
            with open('token.pickle', 'rb') as token:
                creds = pickle.load(token)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not os.path.exists('credentials.json'):
                    raise Exception("Missing credentials.json")
                flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
                creds = flow.run_local_server(port=8080)
            with open('token.pickle', 'wb') as token:
                pickle.dump(creds, token)

        self.service = build('drive', 'v3', credentials=creds)

    def extract_file_id(self, link):
        if '/file/d/' in link:
            return link.split('/file/d/')[1].split('/')[0]
        elif 'id=' in link:
            return link.split('id=')[1].split('&')[0]
        return link

    def download_video(self, file_id, output_path):
        request = self.service.files().get_media(fileId=file_id)
        with open(output_path, 'wb') as f:
            downloader = MediaIoBaseDownload(f, request)
            done = False
            while not done:
                status, done = downloader.next_chunk()
        return output_path

    def normalize_video(self, input_path, output_path):
        """
        Re-encode the video to a consistent format (H.264 + AAC, 30fps, same width).
        Ensures smooth merging.
        """
        (
            ffmpeg
            .input(input_path)
            .output(
                output_path,
                vcodec='libx264',
                acodec='aac',
                vf='fps=30,scale=1280:-1',  # Normalize frame rate & resolution
                preset='medium',
                crf=23
            )
            .run(cmd=self.ffmpeg_path, overwrite_output=True)
        )
        return output_path

    def merge_videos(self, video1_path, video2_path, output_path):
        """
        Merge two videos sequentially (end-to-end) using ffmpeg concat safely.
        """
        list_file = os.path.join(self.temp_dir, "concat_list.txt")
        with open(list_file, "w", encoding="utf-8") as f:
            f.write(f"file '{os.path.abspath(video1_path)}'\n")
            f.write(f"file '{os.path.abspath(video2_path)}'\n")

        (
            ffmpeg
            .input(list_file, format='concat', safe=0)
            .output(
                output_path,
                vcodec='libx264',
                acodec='aac',
                preset='medium',
                crf=23
            )
            .run(cmd=self.ffmpeg_path, overwrite_output=True)
        )
        return output_path

    def merge_side_by_side(self, video1_path, video2_path, output_path):
        """
        Merge two videos side-by-side using ffmpeg hstack.
        Automatically resizes to match heights.
        """
        # Get video info
        probe1 = ffmpeg.probe(video1_path, cmd=self.ffmpeg_path)
        probe2 = ffmpeg.probe(video2_path, cmd=self.ffmpeg_path)
        h1 = int(probe1["streams"][0]["height"])
        h2 = int(probe2["streams"][0]["height"])

        # Resize video2 if needed
        resize_filter = None
        if h1 != h2:
            resize_filter = f"scale=-1:{h1}"

        input1 = ffmpeg.input(video1_path)
        input2 = ffmpeg.input(video2_path)

        if resize_filter:
            input2 = input2.filter("scale", -1, h1)

        (
            ffmpeg
            .filter([input1, input2], 'hstack')
            .output(output_path, vcodec='libx264', acodec='aac', crf=23)
            .run(cmd=self.ffmpeg_path, overwrite_output=True)
        )
        return output_path

    def upload_to_drive(self, file_path, folder_id=None):
        file_name = os.path.basename(file_path)
        file_metadata = {'name': file_name}
        if folder_id:
            file_metadata['parents'] = [folder_id]

        media = MediaFileUpload(file_path, resumable=True)
        file = self.service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id, webViewLink'
        ).execute()
        return file

    def cleanup(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def process(self, video1_link, video2_link, output_folder_id=None, side_by_side=False):
        try:
            self.authenticate()
            v1_id = self.extract_file_id(video1_link)
            v2_id = self.extract_file_id(video2_link)

            v1_path = os.path.join(self.temp_dir, 'video1.mp4')
            v2_path = os.path.join(self.temp_dir, 'video2.mp4')
            v1_norm = os.path.join(self.temp_dir, 'video1_norm.mp4')
            v2_norm = os.path.join(self.temp_dir, 'video2_norm.mp4')
            merged_path = os.path.join(self.temp_dir, 'merged.mp4')

            print("⬇️ Downloading videos...")
            self.download_video(v1_id, v1_path)
            self.download_video(v2_id, v2_path)

            print("⚙️ Normalizing videos for consistent format...")
            self.normalize_video(v1_path, v1_norm)
            self.normalize_video(v2_path, v2_norm)

            print("🎬 Merging videos...")
            if side_by_side:
                self.merge_side_by_side(v1_norm, v2_norm, merged_path)
            else:
                self.merge_videos(v1_norm, v2_norm, merged_path)

            print("☁️ Uploading merged video to Google Drive...")
            result = self.upload_to_drive(merged_path, output_folder_id)

            print("✅ Merge complete!")
            return result
        finally:
            self.cleanup()
