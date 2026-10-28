ODDS DATA LAB WEB FINAL
1) pip install -r requirements.txt
2) streamlit run app.py

Akis:
- MAÇLARI ÇEK: günün futbol maçlarını Mackolik livescores JSON'dan alır.
- İDDAA ORANLARINI BAĞLA: kamuya açık eski Mackolik İddaa Programı sayfasındaki MS 1-X-2 ve varsa 2.5 oranlarını eşleştirir.
- ANALİZ: 58.398+ geçmiş maçta ±0.05 MS oran benzerliği ile gerçek FT/HT sonuç istatistiklerini gösterir.
- SONUÇLARI ARŞİVLE: state=post, FT+HT doğrulanmış ve MS oranı olan maçları ana matches tablosuna bir kez ekler.
- Kaynak erişilemezse oran uydurmaz; maç ORAN BEKLİYOR durumunda kalır.

Not: Streamlit'in uyuması zamanlayıcı değildir. Kesintisiz sabah otomasyonu için morning_job.py bir cron/GitHub Actions/sunucu zamanlayıcısından çalıştırılmalıdır.
