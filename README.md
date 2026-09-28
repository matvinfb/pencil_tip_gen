# Gerador de Ponteiras Personalizadas 3D

Gera modelos 3D (`.stl`, `.3mf` ou `.obj`) de ponteiras personalizadas para lápis e canetas a
partir de um nome ou de uma lista de nomes. A peça é o nome em alto-relevo sobre
uma base, com borda de contorno opcional, e um canal passante paralelo à linha do texto onde o
lápis encaixa — o lápis atravessa
o nome no sentido do comprimento, como um "abraço".

Tudo roda em Python puro via linha de comando: nada de OpenSCAD, Blender ou fatiador. O
resultado final é o arquivo de malha.

```
python -m pencil_tip_gen -n ALICE --font-path /usr/share/fonts/TTF/DejaVuSans-Bold.ttf --preview
```

---

## 1. Instalação

O projeto depende de bibliotecas com extensões compiladas (`shapely`, `trimesh`, `manifold3d`),
então use um ambiente virtual:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Testado no Python 3.14. Nenhuma fonte acompanha o repositório: `--font-path` é obrigatório e
aponta para um `.ttf` ou `.otf` da sua máquina.

---

## 2. Uso

```bash
# conferir antes de gerar: sai só o SVG, nenhuma malha
python -m pencil_tip_gen -n ALICE --font-path fonte.ttf --preview-only

# um nome
python -m pencil_tip_gen -n ALICE --font-path fonte.ttf

# vários nomes de uma vez (um por linha, "#" comenta)
python -m pencil_tip_gen -f examples/names.txt --font-path fonte.ttf --yes

# encaixe sextavado, ponta fechada e preview do perfil
python -m pencil_tip_gen -n "Ana Júlia" --font-path fonte.ttf \
    --hole-shape hexagon --closed-end right --preview --format 3mf
```

Os arquivos saem em `output/` com o nome em minúsculas e sem acentos (`Ana Júlia` →
`ana_julia.stl`). Há dois previews, independentes um do outro:

* `--preview` → `ana_julia.svg`, desenho técnico na escala 1:1 com a silhueta, o contorno das
  letras, o canal tracejado, a seção transversal e as cotas.
* `--preview-3d` → `ana_julia_3d.png`, a peça renderizada em dois ângulos: de cima, para ler o
  nome e ver o relevo; e de frente para a boca do canal, para ver quanto material o abraça. Leva
  alguns segundos por nome.

### Conferir antes de gerar

`--preview-only` roda o pipeline inteiro — inclusive o booleano, que valida a malha — mas grava
**só o SVG**. Serve para ajustar parâmetros num laço rápido:

```bash
python -m pencil_tip_gen -f nomes.txt --font-path fonte.ttf --preview-only
python -m pencil_tip_gen -f nomes.txt --font-path fonte.ttf --preview-only --letter-spacing -0.5
```

A malha continua sendo construída e conferida de propósito: sem isso o preview mostraria as
medidas de uma peça que talvez nem feche, e o booleano custa quase o mesmo que montar o perfil.
Nesse modo o limite de comprimento vira aviso em vez de pergunta — quem está conferindo quer ver
o exagero na tela — e o `--overwrite` não é exigido, já que nenhuma malha é gravada.

`-h` lista todos os parâmetros.

---

## 3. Geometria da peça

Os eixos valem para todo o projeto:

| Eixo | Significado |
|------|-------------|
| **X** | direção da escrita — e do canal do lápis |
| **Y** | altura das letras |
| **Z** | profundidade da extrusão |

O canal exige uma seção mínima de material em Y e em Z:

```
seção = furo + tolerância + 2 × parede     →     7.5 + 0.2 + 2 × 3.0 = 13.7 mm
```

Para garantir essa seção **e** manter as letras presas umas às outras, o perfil 2D é montado em
camadas unidas:

```
        ┌──────────────────────────────────┐
        │   A   L   I   C   E              │  letras (altura automática)
        │ ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓ │  espinha: barra de 13.7 mm
        │ ▓▓▓▓( ● canal ⌀7.7 )▓▓▓▓▓▓▓▓▓▓▓▓ │  atravessando o nome inteiro
        │ ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓ │
        └──────────────────────────────────┘
```

1. **Letras** — contornos da fonte, escalados e unidos.
2. **Borda** (`--enable-border`, desligada por padrão) — offset de 1 mm ao redor das letras.
3. **Espinha** (`--spine`, ligada por padrão) — barra retangular de altura igual à seção, na
   largura toda da peça, alinhada em `--hole-align` (padrão `bottom`, a base das letras).

Com a espinha, a parede mínima ao redor do canal é **garantida por construção**, e não por
tentativa e erro. O que ela não alcança — pingo do "i", til, acentos, palavras separadas por
espaço — é ligado por uma **barra de suporte** automática, pelo menor caminho até o corpo
principal.

### `--no-spine`: peça só de letras

A espinha é **reforço, não requisito**. Com `--no-spine` ela some e o canal atravessa as próprias
letras; quem segura a peça é a sobreposição entre elas (o mesmo aperto descrito abaixo). O
resultado é bem mais leve — "Matheus" cai de 15,6 cm³ para 8,5 cm³ — e o lápis passa a serpentear
por dentro das letras em vez de correr por uma barra.

O preço é a parede: sem a barra o canal vaza nas contra-formas ("o", "a", "e") e nos vãos entre
letras. Isso deixa de ser garantia e passa a ser **medida**: o script reporta quanto do canal tem
parede cheia (tipicamente 50–60% sem espinha, 100% com ela) e avisa. A malha continua estanque —
o que muda é o quanto de material abraça o lápis.

Sem espinha **e** sem borda não existe base para as letras subirem, então o relevo é ignorado (em
vez de engrossar a peça inteira à toa) — o relatório diz isso quando acontece.

### Relevo: como o nome fica legível

A espinha cobre a parte de baixo das letras e, com a borda ligada, o offset ainda preenche os
vãos — a silhueta sozinha vira um bloco e não se lê nada. Por isso a peça tem **duas alturas**:

```
   z = 15.7 ├─────  ▓▓▓ letras ▓▓▓                    ← --relief (2 mm)
   z = 13.7 ├───────────────────────────────────────  ← topo da base
            │  espinha, borda e barras de suporte
            │            ( ● canal do lápis )
   z =  0   └───────────────────────────────────────  ← fundo plano
```

A base vai de zero até `--depth`; as letras vão até `--depth + --relief`. O fundo fica plano e o
nome sobressai numa face só.

### Silhueta: letras encostadas (padrão) ou borda

Por padrão **não há borda**: as letras são apertadas até se encostarem umas nas outras, e são
elas mesmas que formam a silhueta. Cada letra desliza para a esquerda até tocar a anterior, mais
`--letter-overlap` (0.4 mm) para a solda ser um pescoço de verdade e não um ponto. Isso mantém o
desenho das letras legível **e** encurta bastante o nome — "Matheus" em Comic Neue cai de 103 mm
para 86 mm, passando a caber no limite do lápis.

Espaços entre palavras não são apertados; ali quem segura as duas metades é a espinha.

Com `--enable-border` o comportamento antigo volta: espaçamento natural da fonte e um offset que
solda tudo. Nesse caso o aperto se desliga sozinho (o offset já preenche os vãos) e é o relevo
que torna o nome legível. `--tighten`/`--no-tighten` força qualquer combinação.

### Altura automática das letras

Sem `--text-height`, a altura é escolhida sozinha: a **maior altura que ainda cabe** em
`--max-length`, já que a largura é linear na altura. O resultado é limitado entre

* o piso de legibilidade — `seção + --min-letter-exposure` (13.7 + 6 = 19.7 mm), abaixo do qual
  a espinha cobre quase toda a letra e a peça vira um tijolo; e
* o teto `--max-text-height` (30 mm), para nomes curtos não virarem placas.

Um `--max-text-height` explícito abaixo do piso de legibilidade é obedecido (com aviso) — quem
nunca cede é o piso estrutural, a seção do furo.

A largura seria linear na altura se as letras não fossem apertadas; como o aperto encurta o nome
numa proporção que só se sabe medindo, o script parte da estimativa linear e corrige com poucas
medidas reais. Assim as duas regras que brigam entre si (parede mínima e comprimento máximo) se
resolvem numa conta só. Quando nem no piso o nome cabe, entra a confirmação interativa.

---

## 4. Parâmetros

### Encaixe do lápis

| Flag | Padrão | Descrição |
|------|--------|-----------|
| `--hole-size` | `7.5` | Bitola do encaixe, em mm. |
| `--hole-shape` | `circle` | `circle`, `triangle`, `square`, `hexagon`, `octagon`. |
| `--hole-size-mode` | `circum` | `circum` lê `--hole-size` como diâmetro circunscrito; `inscribed`, como distância entre faces (paquímetro num lápis sextavado). |
| `--tolerance` | `0.2` | Folga somada ao perfil, compensando a expansão do plástico. |
| `--chamfer` | `1.0` | Chanfro de entrada de 45° nas bocas abertas. Reduzido sozinho em canais curtos. |
| `--closed-end` | `none` | `left` ou `right` fecham uma ponta, virando ponteira de encaixar no topo. |
| `--cap-thickness` | `2.0` | Espessura da tampa da ponta fechada. |
| `--hole-align` | `bottom` | Onde o canal fica na altura das letras: `bottom`, `center`, `top`. |
| `--hole-offset-y` | `0.0` | Ajuste fino do eixo. |
| `--hole-rotation` | `0.0` | Giro do perfil, em graus. |
| `--hole-segments` | `64` | Lados usados para aproximar o círculo. |

### Estrutura

| Flag | Padrão | Descrição |
|------|--------|-----------|
| `--min-wall-thickness` | `3.0` | Material sólido ao redor do canal, em todas as direções. |
| `--max-length` | `87.5` | Metade de um lápis novo de 175 mm. |
| `--spine` / `--no-spine` | **ligado** | Barra central de reforço que fecha a parede em volta do canal. |
| `--enable-border` / `--no-border` | **desligado** | Borda de silhueta ao redor das letras. |
| `--border-width` | `1.0` | Offset da borda, quando ligada. |
| `--relief` | `2.0` | Quanto as letras sobem acima da base. Ignorado quando não há base (`--no-spine` com `--no-border`). |
| `--tighten` / `--no-tighten` | automático | Aperta as letras até se encostarem. Padrão: liga sem borda, desliga com borda. |
| `--letter-overlap` | `0.4` | Sobreposição entre letras apertadas. |
| `--struts` / `--no-struts` | ligado | Barras de suporte para pingos e acentos soltos. |
| `--strut-width` | `1.2` | Espessura dessas barras. |
| `--min-feature` | `0.8` | Abaixo disso o script avisa que há detalhe fino demais. |

### Texto e malha

| Flag | Padrão | Descrição |
|------|--------|-----------|
| `--font-path` | *obrigatório* | Arquivo `.ttf` ou `.otf`. |
| `--text-height` | automático | Fixa a altura das letras, em mm. |
| `--max-text-height` | `30.0` | Teto da altura automática. |
| `--min-letter-exposure` | `6.0` | Letra que deve sobrar acima da espinha. |
| `--depth` | = seção | Profundidade da **base** (nunca menor que a seção). |
| `--letter-spacing` | `0.0` | Espaço extra entre letras, aplicado depois do aperto; aceita negativo. |
| `--curve-tolerance` | `0.05` | Erro máximo ao achatar as curvas da fonte. |

### Saída e execução

| Flag | Padrão | Descrição |
|------|--------|-----------|
| `--name` / `-n` | — | Nome a gerar; pode repetir. |
| `--file` / `-f` | — | `.txt` com um nome por linha. |
| `--output-dir` / `-o` | `output` | Pasta de saída. |
| `--format` | `stl` | `stl`, `3mf` ou `obj`. |
| `--preview` | desligado | Grava também o SVG do perfil (desenho técnico 1:1). |
| `--preview-3d` | desligado | Grava um PNG com a peça renderizada em 3D. |
| `--preview-only` | desligado | Grava só o SVG: confere as medidas sem escrever malha. |
| `--overwrite` | desligado | Sobrescreve arquivos existentes. |
| `--yes` / `-y` | desligado | Não pergunta nada. |
| `--strict` | desligado | Falha em vez de perguntar. |
| `--continue-on-error` | desligado | Segue o lote depois de um erro. |
| `--quiet` / `-q` | desligado | Imprime só os caminhos gerados. |

---

## 5. Validações

1. **Parede mínima** — com a espinha é garantida por construção: ela tem exatamente a altura da
   seção, a extrusão nunca é mais rasa que ela e o canal fica centrado nos dois eixos. Com
   `--no-spine` a garantia cai e vira medida. Nos dois casos o script mede, depois do booleano, a
   casca entre o furo e o furo + parede, e reporta a fração que é material de verdade.
2. **Comprimento** — passando de `--max-length`, o terminal pede confirmação `[Y/n]`. `--yes`
   dispensa a pergunta e `--strict` transforma em erro. Sem terminal para responder (lote, pipe,
   CI), a execução falha explicando que falta `--yes`. Em `--preview-only` a regra vira aviso.
3. **Peça conexa** — se sobrar algum pedaço solto mesmo depois das barras de suporte, o script
   falha em vez de exportar uma malha que sairia em duas partes.
4. **Malha fechada** — o resultado é conferido como *watertight* e volume válido antes de gravar.
5. **Detalhe mínimo** — regiões mais finas que `--min-feature` viram aviso, não erro.

---

## 6. Arquitetura

| Módulo | Responsabilidade |
|--------|------------------|
| `config.py` | `TipParams`/`OutputOptions`, validação e valores derivados (seção, circunraio). |
| `fonts.py` | `fontTools` → polígonos do `shapely`: achatamento de Bézier e preenchimento par-ímpar por camadas de aninhamento. |
| `profile2d.py` | Escala, borda, espinha, barras de suporte, saneamento e checagens 2D. |
| `holes.py` | Perfil do canal e o cortador 3D, gerado por *loft* de anéis (a mesma rotina serve para círculo e polígonos). |
| `solid.py` | Extrusão, subtração booleana (`manifold3d`) e validação da malha. |
| `export.py` | `.stl`/`.obj` pelo trimesh e um escritor `.3mf` mínimo próprio. |
| `preview.py` | SVG 1:1 do perfil. |
| `preview3d.py` | Render 3D: câmera, rasterizador com z-buffer e escritor de PNG. |
| `report.py` | Resumo no terminal e tabela do modo lote. |
| `cli.py` | Flags, modo lote e a confirmação de comprimento. |

Detalhes de implementação que valem menção, porque foram problemas reais e não escolhas de
estilo:

* **Aninhamento por vértice.** Um ponto interno do contorno externo do "A" cai dentro da
  contra-forma e faria a letra inteira ser lida como furo; um vértice do contorno nunca é
  ambíguo, porque contornos de fonte não se cruzam.
* **Preenchimento por camadas.** Fontes CFF desenham letras com traços sobrepostos e contornos
  auto-intersectantes. Cada contorno é saneado e as camadas de aninhamento são unidas e
  subtraídas alternadamente, o que também resolve ilha dentro de furo (`%`, `@`).
* **`simplify(0)` antes de extrudar.** A união da borda com a espinha deixa vértices colineares
  no meio de arestas retas; o triangulador descarta os triângulos degenerados que eles geram e a
  malha nunca fecha.
* **Fechamento morfológico.** Onde duas partes se encostam num ponto só, o contorno "pinça" e a
  extrusão sai com aresta solta — dilatar e erodir por uma fração de milímetro transforma o
  contato num pescoço de verdade.
* **Z-buffer no render 3D, não algoritmo do pintor.** Ordenar triângulos por profundidade e
  desenhar do fundo para a frente é bem mais curto, mas a peça é oca: as faces do canal têm
  profundidade média menor que a do painel grande à frente delas e aparecem desenhadas por cima,
  como listras que não existem. Num render feito para conferir, isso é pior que não ter render.
* **Detecção de pinça por varredura ordenada, não por grade.** Duas letras que se encostam sem
  sobreposição deixam dois vértices a frações de nanômetro um do outro; arredondar numa grade os
  separa quando o par cai em células vizinhas, e o resultado ainda muda se a peça for transladada.

---

## 7. Testes

```bash
.venv/bin/pytest
```

Os testes cobrem extração de glifos, regras do perfil 2D, geometria do canal, a malha final e a
CLI ponta a ponta. As verificações que importam são geométricas: a malha é estanque, um cilindro
da bitola do lápis atravessa a peça sem tocar material, e a casca entre o furo e o furo + parede
é 100% sólida. A fonte de teste é procurada no sistema; sem nenhuma delas, os testes são pulados.
