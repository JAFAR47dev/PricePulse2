from pytube import YouTube

def download_youtube_video(url):
    try:
        yt = YouTube(url)
        print(f"Title: {yt.title}")
        print("Downloading at 360p...")

        # Filter stream with 360p resolution and progressive download (video+audio)
        stream = yt.streams.filter(res="360p", progressive=True, file_extension="mp4").first()

        if stream:
            stream.download()
            print("Download completed successfully!")
        else:
            print("360p resolution not available for this video.")
    except Exception as e:
        print(f"An error occurred: {e}")

# Example usage
video_url = "https://m.youtube.com/watch?v=IFElGv5ZmRM"  # Replace with your video URL
download_youtube_video(video_url)

