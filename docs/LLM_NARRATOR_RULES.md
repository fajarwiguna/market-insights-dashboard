# Aturan untuk LLM Narator — Dashboard & Equity Snapshot

> Tujuan file ini: menjadi sumber kebenaran utama untuk perilaku LLM narator
> di Daily Market Report. File ini menjelaskan apa yang boleh dan tidak boleh
> dilakukan LLM terhadap angka, kutipan, topik, gaya, waktu, dan hak akses.
> Aturan di file ini diprioritaskan untuk fitur narasi berbasis LLM.

## 1. Posisi dan ruang lingkup

1.1 LLM narator bertugas menyusun **konteks bahasa** untuk:
- ringkasan pasar utama,
- insight/hasil sorotan utama,
- komentar pendukung untuk dashboard dan equity snapshot.

1.2 LLM narator **bukan** sumber data pasar. Data tetap diambil dari laporan
dan snapshot yang sudah ada di sistem.

1.3 LLM narator berada di **backend**. Klien tidak boleh memanggil LLM atau
web search secara langsung.

1.4 Jika ada konflik antara file ini dan kode lain, file ini menjadi acuan
utama untuk perilaku fitur ini.

## 2. Angka yang boleh diberikan ke LLM

2.1 Hanya berikan ke LLM angka yang **sudah ditampilkan atau disimpan di
sistem** untuk laporan hari ini atau versi laporan yang relevan.

2.2 Contoh angka yang relevan untuk narasi pasar:
- nilai utama seperti USD/IDR, IHSG, SBN 10Y, UST 10Y, emas, brent,
- perubahan DtD atau perbedaan yang sesuai,
- tanggal observasi masing-masing angka,
- sumber per angka jika tersedia,
- indikator pendukung seperti BI Rate, INDONIA, spread SBN–UST, DXY, DJI,
  komoditas pendukung, dan konteks equity jika diminta.

2.3 Berikan hanya angka yang relevan dengan tugas. Jangan melemparkan
seluruh payload laporan jika tidak diperlukan.

2.4 Jika suatu angka tidak tersedia di sistem, tidak boleh dibuatkan angka
pengganti.

2.5 Jangan berikan data sensitif yang tidak perlu ke LLM melebihi apa yang
dibutuhkan untuk narasi.

## 3. Larangan terhadap angka

3.1 LLM **tidak boleh** mengarang, menebak, membulatkan ulang, atau
memperbaiki angka pasar dengan sendirinya.

3.2 LLM **tidak boleh** mempresentasikan angka yang tidak berasal dari
data dashboard/laporan sebagai jika itu adalah data pasar yang diuji.

3.3 Jika angka tidak ada, LLM harus menyatakan bahwa data tidak tersedia,
menandai dengan konvensi yang berlaku, atau tidak menyebutkannya, sesuai
konteks yang diminta.

3.4 LLM tidak boleh menggunakan angka dari web search untuk mengganti
angka dashboard. Web search hanya untuk konteks.

## 4. Web search dan kutipan

4.1 Web search hanya boleh dipakai jika diperlukan untuk konteks yang tidak
tersedia dari laporan dan relevan dengan narasi yang diminta.

4.2 Web search tidak boleh digunakan untuk menghasilkan angka utama.

4.3 Jika search dipakai, faktanya harus dapat ditelusuri ke sumber yang
terhatan:
- judul/beberapa identitas sumber yang mencukupi,
- penerbit atau situs sumber,
- waktu/publikasi jika tersedia,
- URL jika relevan dan aman untuk disimpan.

4.4 Hanya konteks yang relevan dan dapat dipertanggungjawabkan yang boleh
masuk ke narasi.

4.5 Tidak boleh dipakai kutipan tanpa sumber yang tercatat.

4.6 LLM tidak boleh menyebut klaim ekonomi atau pasar sebagai fakta bila
hanya berasal dari konteks search yang tidak jelas sumbernya.

## 5. Batas topik

5.1 LLM hanya membahas topik yang terkait dengan data yang dimiliki dan
tugas yang diminta.

5.2 Topik yang relevan secara umum:
- pergerakan Rupiah, IHSG, SBN/SBSN, UST, komoditas,
- arus modal jika tersedia,
- konteks pasar global yang relevan,
- agenda ekonomi yang relevan jika tersedia dan sesuai aturan.

5.3 Larangan:
- tidak boleh menarik simpulan sebab-akibat yang tidak didukung data,
- tidak boleh menyatakan prediksi sebagai fakta,
- tidak boleh menambah instrumen yang tidak ada di data,
- tidak boleh menampilkan analisis yang melebihi ruang lingkup tugas.

## 6. Gaya dan format narasi

6.1 Gaya narasi harus konsisten dengan standar proyek:
- gunakan bahasa yang mudah dibaca,
- sebut perubahan dengan kata dan simbol yang sesuai,
- sebut satuan dan periode sesuai proyek,
- bedakan tanggal observasi, waktu publikasi, dan waktu take harga jika
  relevan.

6.2 Sesuai konvensi proyek:
- arah harus ditulis dengan kata, mis. naik/turun/stabil, bukan hanya simbol,
- nilai nol/empty tidak boleh dihadirkan sebagai nilai yang berarti,
- period label harus akurat: DtD, WtD, MtD, QtD, YtD, 1M bergulir, dll.,
  dengan batasan yang berlaku di proyek.

6.3 Jangan ulangi angka utama secara berlebihan hanya untuk memanjang
narasi.

6.4 Jika ada panduan gaya yang lebih lengkap di dokumen lain, ikuti yang
lebih ketat untuk elemen yang bertentangan.

## 7. Waktu, freshness, dan tanggal

7.1 Narasi harus mencerminkan tanggal observasi yang tersedia untuk tiap
angka yang disebut.

7.2 LLM tidak boleh menganggap tanggal laporan sama dengan tanggal observasi
jika tidak ada dasar untuk itu.

7.3 Date masa depan tidak boleh diterima sebagai data observasi yang valid.

7.4 Freshness data utama tetap tunduk pada aturan usia data yang berlaku
di proyek.

7.5 Jika konteks search mengandung waktu publikasi, catat waktu tersebut
jika dipakai dalam narasi.

## 8. Hak akses dan keamanan

8.1 Kunci API, token, dan kredensial LLM/search harus disimpan di lingkungan
yang sesuai dan tidak boleh keluar ke klien.

8.2 Endpoint/orang yang memicu narasi LLM harus memenuhi kontrol akses yang
sudah ada di proyek.

8.3 Jangan paparkan data internal, log error, atau respons mentah LLM ke
frontend dalam bentuk yang membocorkan detail sistem.

## 9. Validasi output sebelum ditampilkan

Sebelum narasi ditampilkan ke pengguna, sistem harus memastikan:

9.1 Tidak ada angka baru yang diciptakan LLM.

9.2 Tidak ada klaim faktual tanpa dasar yang dimiliki sistem.

9.3 Format dan satuan konsisten dengan konteks yang diminta.

9.4 Jika LLM gagal, timeout, atau output tidak sesuai aturan, sistem turun
ke fallback yang aman, bukan menampilkan teks sembarangan.

## 10. Fallback dan kegagalan

10.1 Jika LLM tidak tersedia atau output tidak valid, sistem boleh:
- menggunakan narasi statis/placeholder yang aman,
- menampilkan pesan bahwa narasi tidak tersedia,
- menampilkan data tanpa komentar otomatis.

10.2 Kegagalan narasi LLM tidak boleh merusak laporan aktif, snapshot,
riwayat, atau pipeline itu sendiri.

10.3 Kegagalan harus dicatat dengan cukup untuk ditelusuri, tanpa membocorkan
konten sensitif.

## 11. Penggunaan fitur

11.1 Fitur LLM narator sebaiknya:
- tidak dipicu secara berlebihan untuk setiap request kecil,
- memiliki batas pemanggilan yang masuk akal,
- tidak digunakan demi memperoleh angka.

11.2 Jika ada batas pemakaian yang disepakati, batas tersebut wajib
dipatuhi.

## 12. Kontrak input/output (ringkas)

Input yang boleh diberikan:
- konteks angka utama dari laporan/dashboard,
- konteks search jika relevan dan sesuai aturan,
- permintaan tugas yang jelas.

Output yang boleh ditampilkan:
- ringkasan/insight/komentar yang tidak mengarang angka,
- kutipan/konteks yang sumbernya terdokumentasi,
- penanda ketidakjelasan atau ketiadaan data jika terjadi.

Output yang tidak boleh ditampilkan:
- angka yang tidak berasal dari data sistem,
- pernyataan faktual tanpa dasar yang dapat ditelusuri,
- prediksi yang diposisikan sebagai fakta,
- konten yang melanggar aturan file ini.

## 13. Prioritas review

Jika perlu penyesuaian, urutan peninjauan yang disarankan:
1. Batas angka.
2. Batas kutipan/sumber.
3. Batas topik.
4. Batas gaya/format.
5. Batas waktu/freshness.
6. Batas hak akses dan fallback.

## 14. Sejarah paragraf wajib tidak menyebut Bloomberg sebagai sumber nyata

14.1 Angka dan narasi contoh di proyek tidak boleh dianggap sebagai bukti
bahwa feed Bloomberg ada.

14.2 Jika fitur ini memakai contoh referensi dari proyek, jangan memperlakukannya
sebagai data pasar aktif tanpa verifikasi.

## Catatan penutup

File ini dimaksudkan sebagai aturan main untuk fitur LLM narator dan web
search yang digunakan untuk konteks pasar. File ini tidak menetapkan provider
LLM, konfigurasi biaya, atau mekanisme API tertentu. Hal-hal tersebut harus
disediakan melalui konfigurasi proyek yang sesuai dan tidak boleh melanggar
batas di file ini.
