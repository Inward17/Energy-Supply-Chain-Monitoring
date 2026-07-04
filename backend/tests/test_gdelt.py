import requests

url = "https://api.gdeltproject.org/api/v2/doc/doc"
query = '("Strait of Hormuz" OR "Suez Canal" OR "Bab-el-Mandeb" OR "Red Sea" OR "Persian Gulf" OR "Strait of Malacca" OR "crude oil" OR "oil tanker" OR "LNG carrier" OR "oil supply disruption" OR "oil sanctions" OR "refinery attack" OR "pipeline explosion")'
params = {
    "query": query,
    "mode": "ArtList",
    "format": "json",
    "maxrecords": "10",
    "startdatetime": "20231215000000",
    "enddatetime": "20231216000000",
    "sort": "DateDesc"
}
r = requests.get(url, params=params)
print(r.status_code)
if r.status_code == 200:
    data = r.json()
    print("Found articles:", len(data.get("articles", [])))
    if data.get("articles"):
        print(data["articles"][0]["title"])
else:
    print(r.text)
