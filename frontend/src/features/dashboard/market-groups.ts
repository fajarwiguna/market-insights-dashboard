export type CategoryId = "fx" | "gold" | "capital-flow" | "yields" | "macro" | "monetary-operations" | "indices" | "commodities";
export type MarketGroup = {
  id: CategoryId;
  label: string;
  title: string;
  description: string;
  kind: "close" | "gold" | "flow" | "yield" | "macro" | "operation" | "index" | "commodity";
};

export const MARKET_GROUPS: MarketGroup[] = [
  { id: "fx", label: "01 / VALUTA", title: "Kurs", description: "Nilai penutupan tiap instrumen; tanggal pembanding mengikuti kalender sumber.", kind: "close" },
  { id: "gold", label: "02 / EMAS", title: "Harga Emas", description: "Gold Spot, futures sebagai seri terpisah, dan harga dasar Antam 1 gram.", kind: "gold" },
  { id: "capital-flow", label: "03 / ARUS MODAL", title: "Capital Flow", description: "Arus bersih saham dan obligasi dalam USD juta.", kind: "flow" },
  { id: "yields", label: "04 / FIXED INCOME", title: "Bond Yield", description: "Perubahan yield ditampilkan dalam basis point; 1 bp = 0,01 poin persentase.", kind: "yield" },
  { id: "macro", label: "05 / MAKRO", title: "Indicators", description: "Nilai indikator berdasarkan bulan publikasi, bukan perubahan bulanan.", kind: "macro" },
  { id: "monetary-operations", label: "06 / LIKUIDITAS", title: "Operasi Moneter", description: "Posisi akhir periode dari SEKI BI; frekuensi bulanan dan tanggal mengikuti observasi terbaru.", kind: "operation" },
  { id: "indices", label: "07 / EQUITIES", title: "Index", description: "IHSG, indeks global, dan sektor IDX-IC.", kind: "index" },
  { id: "commodities", label: "08 / KOMODITAS", title: "Commodity", description: "Harga, unit kontrak, dan perubahan lintas periode.", kind: "commodity" },
];
