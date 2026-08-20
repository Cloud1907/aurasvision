#!/usr/bin/env python3
"""Dil kapsamının TEK tanımı — "bu dosya kaynak kod mu?" sorusu.

Neden tek tanım: aynı soru üç ayrı yerde ayrı listeyle cevaplanıyordu
(H. Demir denetimi, 2026-08-15) ve listeler ÇOKTAN ayrışmıştı:
  - `bin/kapi.py`     `.mjs .sh .sql` taşıyordu, `bin/kalite.py` taşımıyordu
  - `bin/kalite.py`   `.rs .svelte .vue` taşıyordu, `bin/kapi.py` taşımıyordu
Sonuç: aynı değişiklik bir kapıda "kaynak", diğerinde "görünmez dosya"
oluyordu. Yeni bir dil eklemek üç dosyaya + testlerine dokunmayı gerektiriyor,
biri unutulduğunda sessiz bir kör nokta doğuyordu.

Kural: bir dil BİR kez buraya yazılır; kapılar buradan okur. Bekçi:
tests/test_diller.py — kümeler ayrışırsa test düşer.
"""

# Kaynak kod: değişirse test yükümlülüğü doğurur.
KAYNAK = frozenset({
    ".py", ".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx", ".vue", ".svelte",
    ".cs", ".go", ".java", ".rb", ".php", ".kt", ".swift", ".rs",
    ".sql", ".sh",
})

# Görünür yüzey: birim testi yetmez, TIKLAMA kanıtı istenir.
GORUNUR = frozenset({
    ".tsx", ".jsx", ".vue", ".svelte", ".cshtml", ".razor", ".html",
    ".css", ".scss",
})

# Fonksiyon gövdesi süslü parantezle sınırlanan diller (karmaşıklık analizi).
# Ruby (def…end) ve Python burada DEĞİL — "hepsi analiz edildi" demek dürüst
# olmazdı; analiz edilmeyen dosya kapsam raporunda 'yalnız satır sayılan'
# olarak görünür.
SUSLU = frozenset({
    ".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx", ".vue", ".svelte",
    ".cs", ".go", ".java", ".php", ".kt", ".swift", ".rs",
})

# Kalite ratchet'inin ölçtüğü küme: kaynak, ama kabuk/SQL hariç — onlarda
# "fonksiyon" ve "karmaşıklık" ölçüsü anlamlı değildir.
KALITE = KAYNAK - {".sh", ".sql"}


def kaynak_mi(yol):
    """Yol bir kaynak kod dosyası mı (uzantıya göre)."""
    return yol.lower().endswith(tuple(KAYNAK))


def gorunur_mu(yol):
    """Yol görünür yüzey mi (uzantıya göre; dizin kuralı çağıranındır)."""
    return yol.lower().endswith(tuple(GORUNUR))
