# CrossBottle: alternativa gratuita ao CrossOver para Mac

**Rode a Steam, jogos e programas de Windows no macOS (Apple Silicon M1, M2, M3, M4), de graça e com código aberto.**

[English](README.md)

O CrossBottle é um gerenciador de "bottles" (garrafas) do Wine para Mac. Ele instala o Wine e o DXVK,
que são de código aberto, guarda cada programa de Windows na sua própria garrafa e cria apps de Mac de
verdade para eles. A **Steam aparece como "Steam" no Dock**, com o ícone dela, e não como "wine".

> O CrossBottle é um projeto independente, **sem vínculo com a CodeWeavers ou o CrossOver®**, a Valve
> ou o projeto Wine. Esses nomes aparecem só para explicar a compatibilidade.

## Tutorial: Steam no Mac em 4 passos

Você precisa de um Mac com macOS 14 ou mais novo. Abra o **Terminal** (Cmd + Espaço, digite "Terminal")
e cole uma linha por vez, apertando Enter depois de cada uma.

**1. Instale o Rosetta** (só em Mac com chip Apple M1/M2/M3/M4; uma vez só):

```bash
softwareupdate --install-rosetta --agree-to-license
```

**2. Baixe o CrossBottle:**

```bash
git clone https://github.com/RobbOliver/crossbottle.git
```

Se pedir para instalar as "ferramentas de linha de comando", clique em **Instalar** e repita o comando.

**3. Instale** (baixa o Wine e o DXVK, cerca de 200 MB):

```bash
cd crossbottle && ./install.sh
```

**4. Instale e abra a Steam:**

```bash
crossbottle install-steam --open
```

Pronto. Na primeira vez a Steam baixa a própria atualização, o que leva alguns minutos. Depois disso,
abra a **Steam** pela pasta `~/Applications/CrossBottle`, pelo Launchpad ou pelo Spotlight. Você também
pode arrastar o app para o Dock. Os jogos que você instalar na Steam ficam dentro da mesma garrafa.

**Apareceu `crossbottle: command not found`?** Copie e rode a linha `echo 'export PATH=...'` que o
`install.sh` mostrou no final, feche o Terminal e abra de novo.

## Outros programas de Windows

```bash
crossbottle create MeuApp                                    # cria uma garrafa nova (Windows 10)
crossbottle run MeuApp ~/Downloads/instalador.exe            # roda o instalador
crossbottle shortcut MeuApp 'C:\Program Files\MeuApp\MeuApp.exe' --app-name "MeuApp"
open ~/Applications/CrossBottle/MeuApp.app
```

Para jogos com DirectX 11, ative o DXVK na garrafa: `crossbottle graphics MeuApp dxvk`.

## Comandos principais

| Comando | O que faz |
|---|---|
| `crossbottle install-steam --open` | Garrafa + Steam + correção da tela preta + DXVK + `Steam.app` |
| `crossbottle list` | Lista as garrafas |
| `crossbottle run NOME PROGRAMA` | Roda um `.exe`, `.msi` ou `.bat` |
| `crossbottle shortcut NOME PROGRAMA --app-name "Nome"` | Cria um app de Mac com nome e ícone próprios |
| `crossbottle graphics NOME dxvk` | Ativa o DXVK (DirectX 10/11) |
| `crossbottle export NOME arquivo` / `import arquivo` | Faz backup e restaura uma garrafa |
| `crossbottle delete NOME` | Apaga uma garrafa |

## Perguntas frequentes

**É um crack ou cópia do CrossOver?** Não. Não tem nenhum código do CrossOver. É um gerenciador
pequeno, escrito do zero, em cima de projetos públicos de código aberto (Wine, DXVK, MoltenVK).

**Quais jogos funcionam?** Muitos jogos DirectX 9/10/11 que rodam no Wine. Jogos DirectX 12 e jogos
com anti-cheat de kernel (Valorant e vários jogos online competitivos) não funcionam.

**Instalar jogos da Steam num HD externo.** Rode `crossbottle drive Steam E: /Volumes/SeuDisco`,
reinicie a Steam e vá em Configurações → Armazenamento → Adicionar unidade → `E:`. O comando também
marca a unidade como disco fixo no Wine; sem isso a Steam diz que a biblioteca "não está montada".

**A interface da Steam está lenta.** Ela é desenhada pelo processador. Testamos a GPU (Vulkan e OpenGL)
e nenhuma funciona direito neste Wine: no Vulkan a área da loja fica preta por minutos. A página da loja
sozinha deixa a interface perto de 100% de um núcleo (animações e trailers); abrir a Steam na Biblioteca e
desligar a reprodução automática de vídeos na loja ajuda. Um download de jogo em andamento também deixa a loja bem mais lenta. A Steam também roda pelo Rosetta. Na Steam, ative Configurações → Biblioteca → *Modo de baixo
desempenho*, desative Configurações → Interface → *Rolagem suave*, ou use Exibir → *Modo compacto*. Em Macs
com 8 GB, feche outros apps pesados. Os jogos não são afetados: eles usam a GPU.

**A Steam atualizou e a tela ficou preta.** Abra a Steam pelo app do CrossBottle, que reaplica a
correção sozinho, ou rode `crossbottle cefwrap Steam`.

**Como desinstalar?** Apague `~/Applications/CrossBottle`, `~/Library/Application Support/CrossBottle`,
`~/Library/Logs/CrossBottle` e `~/.local/bin/crossbottle`.

Detalhes técnicos estão no [README em inglês](README.md#how-it-works).

*Palavras-chave: alternativa ao CrossOver, CrossOver grátis, CrossOver gratuito Mac, rodar programas de
Windows no Mac, Steam no Mac M1, jogos de Windows no Mac, Wine para macOS, alternativa ao Whisky.*
