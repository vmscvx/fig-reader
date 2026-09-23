# fig-reader

Чтение файлов Figma `.fig` без Figma и без API: узлы документа в JSON, поиск
кадров, дерево с текстами и размерами, отрисовка кадра в HTML для сверки
глазами. Чистый Python 3.14 (нужен встроенный `compression.zstd`), без
зависимостей.

Зачем: макет лежит файлом («Save local copy»), доступа к проекту в Figma нет, а
размеры, отступы, цвета и тексты нужно снимать точно, а не на глаз по PNG.

## Быстрый старт

```bash
python readfig.py "макет.fig" canvas.json   # ~1 мин на 380 МБ: 47 619 узлов, 4 200 блобов
python fig.py find "Каталог"                # кадры, секции и символы по подстроке в имени
python fig.py tree 706:38090 3              # поддерево: тип, guid, имя, x,y, размер, текст
python render.py "макет.fig" 706:38090 frame.html   # кадр в HTML (картинки вшиты)
python test_kiwi.py                         # проверка декодера на известных байтах
```

`fig.py` и `render.py` читают `canvas.json` из текущей папки или из переменной
`FIG_CANVAS`. `render.py` берёт картинки из самого `.fig`, поэтому ему нужен и он.

HTML открывается браузером напрямую. Для просмотра целиком на узком экране:
`document.body.style.zoom = innerWidth / 1920`.

## Формат

`.fig` из «Save local copy» — zip: `canvas.fig`, `thumbnail.png`, `meta.json`,
`images/<sha1>` (картинки заливок по хешу).

`canvas.fig`:

    "fig-kiwi"          8 байт
    версия              uint32 LE
    кусок 0             uint32 LE длина + kiwi-схема (raw deflate)
    кусок 1             uint32 LE длина + сообщение (zstd, если начинается
                        с 28 B5 2F FD, иначе raw deflate)

Схема самоописательна (формат [kiwi](https://github.com/evanw/kiwi) Эвана
Уоллеса, сооснователя Figma), поэтому декодер универсальный: сначала читает
схему, потом по ней — сообщение типа `Message`. Чтение значений повторяет
`js/bb.ts` и `js/binary.ts` из kiwi один в один:

- `uint` — varint до 5 байт, результат uint32; `int` — он же зигзагом;
- `uint64`/`int64` — varint, девятый байт берётся целиком;
- `float` — 0 одним байтом, иначе 4 байта LE с экспонентой, сдвинутой в младшие
  биты (`bits = (bits << 23) | (bits >>> 9)`);
- `string` — UTF-8 до нулевого байта; `byte[]` — длина varint + байты;
- встроенные типы в схеме — отрицательные: `~индекс` в
  `[bool, byte, int, uint, float, string, int64, uint64]`;
- struct — поля подряд; message — пары «номер поля + значение» до нуля.

В `Message`: `nodeChanges` — плоский список всех узлов (дерево собирается по
`parentIndex.guid`, порядок детей — `parentIndex.position`), `blobs` — байтовые
данные, на которые узлы ссылаются номером.

### Что где лежит в узле

- текст — `textData.characters`; **`fillPaints` у TEXT — цвет букв, не фон**;
- позиция — `transform.m02/m12` относительно родителя, размер — `size`;
- картинка — `fillPaints[].image.hash` → файл `images/<hex>` в zip;
  кадрирование (`imageScaleMode` STRETCH — это CROP из API, и TILE) —
  `fillPaints[].transform`: точка картинки в пикселях → узел =
  `scale(w,h) · T⁻¹ · scale(1/imgW, 1/imgH)`;
- инстанс — `symbolData.symbolID` (мастер) и `symbolData.symbolOverrides`
  (переопределённые тексты/заливки по `guidPath`; ключ — `overrideKey` узла,
  если есть, иначе `guid`); оверрайд с путём на сам мастер красит корень;
- контуры векторов — `fillGeometry[]`/`strokeGeometry[]`: `commandsBlob` —
  номер в `blobs`. Команда — байт, аргументы float32 LE:
  `0` Z, `1` M x y, `2` L x y, `3` Q x1 y1 x y, `4` C x1 y1 x2 y2 x y;
  `windingRule` — `NONZERO` / `ODD`.

## Ограничения отрисовки

`render.py` — чтобы посмотреть, а не для пиксель-в-пиксель: не рисует тени и
размытие, повороты узлов, перестроение auto-layout у растянутых инстансов,
смешанные стили внутри одного текста. Цифры (отступы, размеры, радиусы, цвета)
снимать через `fig.py tree`, а не с картинки.

## Источники

- kiwi: https://github.com/evanw/kiwi (`js/bb.ts`, `js/binary.ts`)
- контейнер: https://openpencil.dev/reference/file-format
- геометрия и кадрирование картинок: https://github.com/open-pencil/open-pencil
  (`packages/core/src/io/formats/svg/paths.ts`, `packages/core/src/canvas/fills.ts`)
