# Validation du calcul de la géométrie

CutLayout ne lit pas les contours dessinés par Seamly2D : il **recalcule** chaque pièce à partir des formules du patron (`.sm2d`) et des mesures (`.smis`), avec le module `src/sm2d_geom.py` (bibliothèque standard de Python seulement). Cette note montre que ce calcul donne le même résultat que Seamly2D.

**Échantillon** : [`samples/patron.sm2d`](../samples/patron.sm2d) + [`samples/mesures.smis`](../samples/mesures.smis), un patron de base buste et manche homme. Les mesures sont relevées dans un tableau de tailles de prêt-à-porter publié en ligne : ce ne sont pas celles d'une personne.

## 1. Comparaison avec Seamly2D

Longueurs relevées dans le **Tableau des variables** de Seamly2D (longueurs de courbes, 4 décimales affichées), comparées au calcul de `sm2d_geom` :

| Courbe | Seamly2D (cm) | `sm2d_geom` (cm) | Écart (cm) |
| --- | --- | --- | --- |
| `SplPath_F2_D1` | 25,3691 | 25,36906 | −0,00004 |
| `SplPath_F2_D1_Seg_1` / `_Seg_2` | 10,8523 / 14,5168 | 10,8523 / 14,5168 | < 0,0001 |
| `SplPath_H2_D1` | 24,4013 | 24,40128 | ≈ 0 |
| `SplPath_H2_D1_Seg_1` / `_Seg_2` | 12,2034 / 12,1979 | 12,2034 / 12,1979 | < 0,0001 |
| `Spl_A_E2` | 8,34367 | 8,34365 | −0,00002 |
| `Spl_G2_G3` | 12,3447 | 12,34469 | −0,00001 |
| `Spl_M4_M` | 25,3686 | 25,36853 | −0,00007 |
| `Spl_M_M5` | 24,4023 | 24,40223 | −0,00007 |

**12 valeurs, écart maximal 0,0001 cm**, soit la limite d'affichage de Seamly2D. Les valeurs calculées ont été fixées avant la lecture de celles de Seamly2D.

Sur cet échantillon, cela établit :

- **la position des points** dont partent ces courbes (A, E2, F2, G2, G3, B5, C5, D1, H2, M, M1, M4, M5) : juste à 0,001 cm près, sinon les longueurs ne coïncideraient pas ;
- **la convention des poignées** de courbe : point de passage + longueur × direction de l'angle, pour les deux poignées de chaque nœud (courbes simples et chemins de courbes) ; angles en degrés, 0° vers la droite, 90° vers le haut ;
- **la longueur d'arc** : le calcul numérique de `sm2d_geom` et celui de Seamly2D concordent à 0,0001 cm.

Ces valeurs sont reprises dans les tests (`tests/geom/test_sm2d_geom.py`, tolérance 0,001 cm).

## 2. Contrôles de cohérence du patron

| Pièce | L × H (cm) | Aire (cm²) | Auto-intersections |
| --- | --- | --- | --- |
| Demi-dos | 28,50 × 70,03 | 1700,9 | 0 |
| Demi-devant | 27,50 × 68,50 | 1576,1 | 0 |
| Manche longue | 38,27 × 65,00 | 1702,3 | 0 |
| Manche courte | 38,27 × 22,00 | 576,2 | 0 |

- Tête de manche − emmanchure : −0,0005 cm (dos), +0,0009 cm (devant). Cible de la méthode de patronnage : 0 ± 0,1 cm.
- Encolure − tour de cou / 2 : +0,188 cm. Cible : 0 à +0,5 cm.
- Milieu dos A–A3 = 67,5 cm. Manche M–M2 = 65,0 cm. Côtés dos et devant : 21,179 cm tous les deux.
- L'aire du dos varie de moins de 0,05 cm² quand on multiplie par 4 la finesse d'échantillonnage des courbes.

## 3. Le cache `length` du fichier n'est pas une référence

Dans le `.sm2d`, certaines courbes portent un attribut `length`. Sur cet échantillon, il **ne correspond pas** à la longueur de la courbe, ni au calcul de `sm2d_geom`, ni à l'affichage actuel de Seamly2D :

| Courbe | Seamly2D et `sm2d_geom` | Attribut `length` du fichier |
| --- | --- | --- |
| `Spl_A_E2` | 8,344 | 8,435 |
| `Spl_G2_G3` | 12,345 | 11,479 |
| `Spl_M4_M` | 25,369 | 22,794 |
| `Spl_M_M5` | 24,402 | 21,412 |

Cause **inconnue**. Une hypothèse plausible, non démontrée : la valeur n'est pas mise à jour quand une formule change après coup. CutLayout ne lit donc **jamais** cet attribut et recalcule toujours les longueurs.

## 4. Précision des contours

- Chaque segment de courbe est échantillonné en 200 points dans CutLayout. L'écart au contour calculé avec 1600 points est inférieur à 0,003 mm.
- Le PDF est relu par les tests : coordonnées exactes à 0,01 mm près (tolérance des tests). L'échelle à l'impression dépend ensuite de l'imprimante, d'où la page d'essai et la correction d'échelle (voir le [tutoriel](tutoriel/README.md#11-calibrer-limprimante)).

## 5. Limites

- **Un seul patron de référence.** D'autres patrons peuvent utiliser des outils non couverts par cette validation.
- **Outils reconnus** : seuls ceux de cet échantillon, plus les fonctions des formules listées dans le [tutoriel](tutoriel/README.md#15-ce-que-cutlayout-lit-dans-un-patron-seamly2d). Tout autre élément est refusé à l'ouverture avec un message qui le nomme : aucune géométrie n'est inventée.
- **Fonctions des formules** autres que `sqrt` : vérifiées contre la bibliothèque mathématique de Python, **pas encore contre Seamly2D**.
- **Contour net seulement** : la marge de couture déclarée dans le patron n'est pas calculée.
- Non lus : crans, droit-fil, étiquettes, lignes intérieures.
