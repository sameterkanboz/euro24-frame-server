from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import StreamingResponse
from PIL import Image, ImageOps, ImageDraw, ExifTags
import io
import requests
import redis

app = FastAPI()

# Redis bağlantısı
r = redis.Redis(
  host='more-mastodon-55368.upstash.io',
  port=6379,
  password='AdhIAAIncDE4ZmEzNjhmZGU1Y2M0MGJlYjk3MmRkMmQ4NWJlNjU2NnAxNTUzNjg',
  ssl=True
)

# Ülke kodları sözlüğü
COUNTRY_CODES = {
    "Türkiye": "tr",
    "Almanya": "de",
    "Fransa": "fr",
    "İtalya": "it",
    "İspanya": "es",
    "Portekiz": "pt",
    "Hollanda": "nl",
    "Belçika": "be",
    "İsviçre": "ch",
    # Diğer ülkeler için kodları buraya ekleyin
}

LEADERBOARD_KEY = "leaderboard"

def add_country_score(country: str):
    r.zincrby(LEADERBOARD_KEY, 1, country)

def get_leaderboard():
    return r.zrevrange(LEADERBOARD_KEY, 0, -1, withscores=True)

def correct_image_orientation(image: Image) -> Image:
    try:
        for orientation in ExifTags.TAGS.keys():
            if ExifTags.TAGS[orientation] == 'Orientation':
                break

        exif = image.getexif()
        if exif is not None:
            orientation = exif.get(orientation)
            print(f"Image EXIF orientation: {orientation}")  # Debugging: log the orientation

            if orientation == 3:
                image = image.rotate(180, expand=True)
            elif orientation == 6:
                image = image.rotate(270, expand=True)
            elif orientation == 8:
                image = image.rotate(90, expand=True)
    except (AttributeError, KeyError, IndexError) as e:
        # cases: image don't have getexif or other issues
        print(f"Error correcting orientation: {e}")  # Debugging: log the error

    return image

@app.post("/upload/")
async def upload_image(country: str = Form(...), file: UploadFile = File(...)):
    if country not in COUNTRY_CODES:
        raise HTTPException(status_code=400, detail="Invalid country selection")

    # Load the input image
    image = Image.open(io.BytesIO(await file.read())).convert("RGBA")
    image = correct_image_orientation(image)

    # Debugging: log the image size and mode after correction
    print(f"Image size after orientation correction: {image.size}, mode: {image.mode}")

    # set the image size as 1/1 aspect ratio
    image_width, image_height = image.size
    if image_width != image_height:
        min_dimension = min(image_width, image_height)
        image = image.crop((0, 0, min_dimension, min_dimension))

    image_width, image_height = image.size

    # Fixed frame dimensions
    border_top = 200
    border_bottom = 800
    border_left = 200
    border_right = 200

    # New image dimensions including the border
    new_width = image_width + border_left + border_right
    new_height = image_height + border_top + border_bottom

    # Create a new image for the framed output
    framed_image = Image.new("RGBA", (new_width, new_height), (0, 0, 0, 0))

    # Download the flag image for the selected country
    country_code = COUNTRY_CODES[country]
    flag_url = f"https://flagcdn.com/w2560/{country_code}.png"
    response = requests.get(flag_url)
    if response.status_code != 200:
        raise HTTPException(status_code=400, detail="Flag image not found")

    flag_image = Image.open(io.BytesIO(response.content)).convert("RGBA")

    # Scale the flag image uniformly to cover the larger dimension of the frame
    flag_width, flag_height = flag_image.size
    scale_factor = max(new_width / flag_width, new_height / flag_height)
    scaled_flag = flag_image.resize((int(flag_width * scale_factor), int(flag_height * scale_factor)))

    # Center the scaled flag image within the border area
    flag_width, flag_height = scaled_flag.size
    left_offset = (flag_width - new_width) // 2
    top_offset = (flag_height - new_height) // 2

    # Crop the necessary parts of the scaled flag image for the top, bottom, left, and right borders
    top_crop = scaled_flag.crop((left_offset, top_offset, left_offset + new_width, top_offset + border_top))
    bottom_crop = scaled_flag.crop((left_offset, flag_height - border_bottom, left_offset + new_width, flag_height))
    left_crop = scaled_flag.crop((left_offset, top_offset, left_offset + border_left, top_offset + new_height))
    right_crop = scaled_flag.crop((flag_width - border_right, top_offset, flag_width, top_offset + new_height))

    # Paste the border sections onto the framed image
    framed_image.paste(top_crop, (0, 0))
    framed_image.paste(bottom_crop, (0, new_height - border_bottom))
    framed_image.paste(left_crop, (0, 0))
    framed_image.paste(right_crop, (new_width - border_right, 0))

    # Paste the original image in the center of the framed image
    framed_image.paste(image, (border_left, border_top))

    # Load and place the Euro 2024 logo bottom right
    euro2024_logo_path = "images/logo.png"
    euro2024_logo = Image.open(euro2024_logo_path).convert("RGBA")
    logo_width, logo_height = euro2024_logo.size
    logo_scale_factor = 0.2
    scaled_logo = euro2024_logo.resize((int(logo_width * logo_scale_factor), int(logo_height * logo_scale_factor)))
    framed_image.paste(scaled_logo, (new_width - logo_width // 5, new_height - logo_height // 5), scaled_logo)

    # Create a circular version of the country flag
    circular_flag_size = 600
    mask = Image.new('L', (circular_flag_size, circular_flag_size), 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((0, 0, circular_flag_size, circular_flag_size), fill=255)

    circular_flag = ImageOps.fit(flag_image, (circular_flag_size, circular_flag_size), centering=(0.5, 0.5))
    circular_flag.putalpha(mask)

    # Draw a border around the circular flag
    border_size = 10
    bordered_circular_flag = Image.new("RGBA", (circular_flag_size + 2 * border_size, circular_flag_size + 2 * border_size), (255, 255, 255, 0))
    draw = ImageDraw.Draw(bordered_circular_flag)
    draw.ellipse((0, 0, circular_flag_size + 2 * border_size, circular_flag_size + 2 * border_size), outline="white", width=border_size)
    bordered_circular_flag.paste(circular_flag, (border_size, border_size), circular_flag)

    # Place the bordered circular flag at the bottom left and same padding values as the euro 2024 logo
    framed_image.paste(bordered_circular_flag, (border_left, new_height - border_bottom + 120), bordered_circular_flag)

    # Add score to leaderboard (increment score by 1 for this example)
    add_country_score(country)

    # Save the resulting image to a byte stream
    img_byte_arr = io.BytesIO()
    framed_image.save(img_byte_arr, format="PNG")
    img_byte_arr.seek(0)

    return StreamingResponse(img_byte_arr, media_type="image/png",
                             headers={"Content-Disposition": "attachment; filename=framed_image.png"})

@app.get("/leaderboard/")
async def leaderboard():
    leaderboard = get_leaderboard()
    return [{"country": country.decode("utf-8"), "score": int(score)} for country, score in leaderboard]
