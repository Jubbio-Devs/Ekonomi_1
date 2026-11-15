# Ekonomi Botu

[JubbioPy](https://pypi.org/project/jubbio/) ile yazılmış, Jubbio için ekonomi botu.

- **Çalış ve kazan:** `.çalış` ile günlük para, transfer, sıralama, profil, envanter
- **Şirketler:** şirket kur, malzeme üret, fiyat belirle, oyunculara veya pazara sat, seviye atla
- **Borsa:** hisse senetleri ve oyuncu şirketlerinin hisseleri, portföy, kâr/zarar
- **Pazar:** dalgalanan malzeme fiyatları
- **Taş-Kağıt-Makas:** bahisli veya bahissiz
- **Pro üyelik:** bot sahibinin verdiği süreli veya kalıcı ayrıcalıklar
- `.` ve `/` ön ekleri, tüm komutlar ayrıca slash komut olarak kayıtlı
- SQLite ile kalıcı veri

## Kurulum

```bash
pip install -r requirements.txt
```

Ortam değişkenlerini ayarlayıp başlatın:

```bash
export BOT_TOKEN=tokeniniz
export OWNER_ID=jubbio_idniz
python main.py
```

## Ayarlar

| Değişken | Varsayılan | Açıklama |
|---|---|---|
| `BOT_TOKEN` | | Bot token'ı (zorunlu) |
| `OWNER_ID` | | Pro ekleyip silebilecek kişinin Jubbio ID'si |
| `BOT_NAME` | `Ekonomi Botu` | Mesajlarda görünen bot adı |
| `CURRENCY` | `coin` | Para birimi adı |
| `CURRENCY_EMOJI` | `🪙` | Para birimi emojisi |
| `PREFIX` | `.` | Ana komut ön eki |
| `PREFIXES` | `. /` | Kabul edilen tüm ön ekler |
| `DATA_DIR` | `./data` | Veritabanı klasörü |
| `SUPPORT_INVITE` | | Destek sunucusu bağlantısı (verilirse `.destek` komutu ve butonlar açılır) |
| `LOGO_URL` | | Yardım menüsünde gösterilecek logo |
| `COLOR` | `F3A921` | Embed rengi (hex) |

## Railway

`railway.json` hazırdır. Depoyu bağlayın, değişkenleri girin ve verilerin kalıcı olması için
servise bir **Volume** ekleyip `/data` yoluna bağlayın, `DATA_DIR=/data` yapın.

## Komutlar

Ön ek `.` veya `/`. Türkçe karakterli ve karaktersiz yazım aynıdır (`.çalış` = `.calis`). 👑 = sadece bot sahibi

### 📌 Genel

| Komut | Açıklama |
|---|---|
| `.yardım [kategori \| komut]` | Yardım menüsü. |
| `.ping` | Botun gecikmesi. |
| `.istatistik` | Bot istatistikleri. |

### 🪙 Ekonomi

| Komut | Açıklama |
|---|---|
| `.çalış` | Çalışıp 50-150 coin kazanırsın (günde 1 kez, Pro: 12 saatte bir ×1.5). |
| `.bakiye [@kullanıcı]` | Norm bakiyeni gösterir. |
| `.gönder @kullanıcı <miktar>` | Başka birine coin gönderir (%5 kesinti, Pro'da kesinti yok). |
| `.zenginler` | En zengin 10 kişi (cüzdan). |
| `.profil [@kullanıcı]` | Ekonomi profilin: servet, şirket, Pro durumu, oyun istatistikleri. |
| `.envanter [@kullanıcı]` | Sahip olduğun malzemeler ve pazar değerleri. |

### 🏢 Şirket ve Pazar

| Komut | Açıklama |
|---|---|
| `.sat <malzeme> <adet\|hepsi>` | Envanterindeki malzemeyi pazara güncel fiyattan satar. |
| `.pazar` | Malzemelerin güncel pazar fiyatları (.sat ile bu fiyattan satarsın). |
| `.şirket <kur\|bilgi\|üret\|fiyat\|sat\|yatır\|çek\|yükselt\|kapat> ...` | Kendi şirketini kur, malzeme üret ve sat. |
| `.market [malzeme]` | Oyuncu şirketlerinin satışa sunduğu malzemeler. |
| `.satınal <şirket sembolü> <adet>` | Bir şirketten malzeme satın alır. |

### 📈 Borsa

| Komut | Açıklama |
|---|---|
| `.borsa [al\|sat <sembol> <adet\|hepsi>] \| [sembol]` | Hisse senedi al-sat. Fiyatlar 10 dakikada bir değişir. |
| `.portföy [@kullanıcı]` | Sahip olduğun hisseler, kâr / zarar. |

### 🎮 Oyunlar

| Komut | Açıklama |
|---|---|
| `.tkm <taş\|kağıt\|makas> [bahis]` | Bota karşı taş-kağıt-makas. Bahis koyarsan kazanınca bahsin kadar kazanırsın. |

### 💎 Pro

| Komut | Açıklama |
|---|---|
| `.pro [@kullanıcı]` | Pro özelliklerini ve Pro durumunu gösterir. |
| `.proekle <ID\|@kullanıcı> <süre\|kalıcı>` 👑 | Kullanıcıya Pro ekler (sadece bot sahibi). Süre varsa mevcut süreye eklenir. |
| `.prosil <ID\|@kullanıcı>` 👑 | Kullanıcının Pro'sunu kaldırır (sadece bot sahibi). |
| `.proliste` 👑 | Pro üyeleri listeler (sadece bot sahibi). |

## Testler

```bash
pip install -r requirements-dev.txt
pytest
```
