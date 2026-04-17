import qrcode

url = "https://web-production-8546b.up.railway.app"
img = qrcode.make(url)
img.save("railway_qr.png")
print("QR Code generated: railway_qr.png")
