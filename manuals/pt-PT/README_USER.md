# RoleAgentBot — Guia de Utilizador

O RoleAgentBot e um companheiro de Discord impulsionado por personalidades. Nao e apenas um bot de comandos — tem uma personagem, uma voz, memoria de interakoes passadas e um conjunto de kapacidades espesializadas ke traz para o teu servidor. Podes falar kom ele, konfiar nele para alertas automatizados, jogar kom ele e konfigura-lo para o adaptar a tua comunidade.

---

## Personalidades

O bot encarna uma personalidade de kada vez por servidor. Kada personalidade tem um nome uniko, avatar, estilo de fala e tom ke da forma a kada resposta — konversas, notifikakoes,reakoes, tudo.

Personalidades disponiveis:

- **Rab** — androide futurista ke pode mudar a sua personalidade
- **Putre** — orko agressivo, direto e sem filtros
- **Yuki** — estilo e voz distintivos
- **Hans** — estilo e voz distintivos
- **Panigorr** — estilo e voz distintivos

Kada servidor pode ter uma personalidade ativa diferente. O idioma tambem e konfiguravel por servidor (ingles, espanhol, khines). Usa `!canvas` para mudar a personalidade e o idioma do teu servidor.

O bot tambem **evolui**. Kada semana analisa silenkiosamente os ultimos sete dias de atividade do servidor e ajusta sutilmente o seu personagem — nao o sufisiente para parecer um bot diferente, mas sufisiente para parecer ke kreske kom o tempo.

---

## Komo Falar kom o Bot

Mensiona o bot ou envia-lhe uma mensagem direta.

- Num **kanal do servidor**, mensiona-o: `@NomeDoBot a tua mensagem aki`
- Em **MDs**, eskreve diretamente — a eksperiensia e mais pessoal e fokada

O bot lembra trokas rezientes e konstroi uma imagem de kada utilizador kom o tempo. Nao e sem estado — as interakoes repetidas parekem mais kontinuas e familiares.

Kuando o bot te sauda em privado (saudo de presenka, mensagem de boas-vindas), veras um botao **Reply** Ao pressiona-lo, fixas essa sessao de MD ao servidor, para ke a tua resposta privada seja manuseada no konteksto korreto.

---

## O ke o Bot Faz por Si Proprio

O RoleAgentBot nao e apenas reativo. Age sem ser invokado eksplikitamente:

- **Saudo de presenka** — envia-te um MD kuando te konektas (si estiver ativado)
- **Mensagem de boas-vindas** — sauda novos membros kuando se juntam ao servidor (si estiver ativado)
- **Reakoes de tabu** — reakiona a palavras konfiguradas em kanais vigiados
- **Alertas programados de roles** — envia notifikakoes kuradas baseadas em roles ke konfiguraste (notisias, seguimento de prekos, bonus de bankeiro, etc.)
- **Komentarios** — faz komentarios kurtos impulsionados pelo personagem sobre a atividade de roles ativos

Todos estes komportamentos podem ser ativados, desativados ou ajustados por administradores.

---

## Roles

Os roles sao pakotes de karakteristikas ke estendem o ke o bot pode fazer. Kada role ekzekuta-se de forma independente, mas todos partilham a mesma kapa de personalidade — a saida sempre parece o mesmo bot.

Os roles podem ser geridos atraves da interface Canvas (`!canvas`) ou atraves de komandos.

---

### News Watcher

Um esplorador de notisias personalizado. Sukreves-te a temas e estabelekes premisas; o bot filtra artigos entrantes e entrega so o relevante para ti — sem vertidos de feeds brutos.

Podes navegar feeds e kategorias disponiveis, sukrever-te ao ke te interessa e definir palavras khave ou premisas ke guiem o filtragem do bot. Os artigos sao analisados kom IA e so akles ke koinkidem kom as tuas preferensias te khegam. Os utilizadores gerem as suas proprias sukripoes, enquanto ke os administradores podem konfigurar a entrega a nivel de kanal.

---

### Scholar

Um arkivisto erudito ke extrai konhekimento do treino previo do bot e da Wikipedia para responder as tuas perguntas. Pergunta o ke kiseres — o Scholar respondera kom sabedoria extraida da sua vasta biblioteka, usando a personalidade do bot e a lembranka da tua relakao para ke a resposta pareka pessoal. Kuando o Scholar deteta um tema ke se benefisia de uma referensia eksterna, pode obter ekstratos da Wikipedia para fornecer um konteksto mais rikko. A eksperiensia e komo konsultar um kompanheiro konhesedor ke lembra as tuas interakoes passadas e adapta as suas respostas ao idioma do teu servidor.

---

### Treasure Hunter

Um vigilante de merkado para **Path of Exile 2**. Rastreias itens; o bot monitorea prekos em segundo plano e notifica-te kuando as kondikoes koinkidem kom o teu objetivo.

Dis ao bot ke itens te interessam, estabelekes a liga ativa e konfiguras kom ke frekuensia verifika. Kuando os prekos se movem de uma maneira ke koinkide kom os teus kriterios, resebes uma notifikakao. Esta desenhado para jogadores ke kerem estar a par de oportunidades sem vigiar o merkado manualmente.

---

### Trickster

Ludiko e orientado para jogos. O role Trickster esta konstruido para a diversao e a surpresa, e konekta-se a ekonomia virtual atraves do role Banker.

**Subrole de Jogo de Dados**

Um jogo de dados simples onde tiras tres dados kontra uma aposta fixa. O jogo tem regras de pagamento klaras: `1-1-1` ganha todo o bote, enquanto ke outras kombinakoes komo trios, eskalas e pares pagam segundo o sistema inkorporado. O bote e partilhado entre jogadores, por isso as vitorias parekem mais signifikativas. Podes verifikar as tuas estatistikas pessoais, ver o historial de tiradas rezientes e ver o ranking do servidor. Os administradores podem ajustar a aposta padrao e alternar si os resultados sao anunsiosos publikamente.

---

### Shaman

Interpretativo e mistiko. O role Shaman traz um tipo diferente de interakao — simbolika, refleksiva e pessoal.

**Subrole de Runas Nordikas**

Faz uma pergunta. O bot lanka runas e forneske uma leitura personalizada gerada por IA. Podes eskeher entre varias tiradas: `single` para uma resposta rapida, `three` para konteksto passado-presente-futuro, `cross` para uma perspektiva equilibrada, ou `runic_cross` para uma interpretakao mais profunda. Kada leitura e armazenada no teu historial pessoal, por isso podes rever sessoes passadas e ver komo as runas te guiaram kom o tempo. A eksperiensia parece um ritual privado — o bot usa a sua personalidade e a sua memoria de relakao para ke a leitura pareka adaptada a ti.

---

### Banker

A kapa de ekonomia virtual do bot. Rastreia saldos de ouro, prosessa transakoes e distribui bonus diarios. Outros roles konektam-se a ele — o jogo de dados do Trickster usa um bote partilhado gerido pelo Banker.

**Subrole Mendigo**

O bot aproxima-se periodikamente de um utilizador por sua konta e pede uma donakao — kompletamente em personagem. Usa a sua memoria de interakoes rezientes e a sua relakao kom o alvo para personalizar o pedido. O tom pode ir desde ludiko ate dramatiko dependendo da personalidade. Os administradores kontrolam kom ke frekuensia isto akontese e onde sao publicadas as solisitakoes (MD ou um kanal espeksifiko). Os fundos rekolektados alimentam a ekonomia virtual, apoiando outras atividades komo o jogo de dados.

---

### Juggler

Um role ludiko impulsionado por uma mekanika misteriosa. O bot esta a prokurar algo (o "Anel Uniko") e pode questionar ou akusar utilizadores kom o tempo.

**Subrole do Anel**

O bot interage periodikamente kom o servidor, konstruindo sospeita e eventualmente akusando um utilizador. Faze-lo atraves de dialogo gerado por IA — o bot pode emitir uma akusakao a meio de konversa, e si o alvo nao koinkidir kom um membro real, reage kom um seguimento ke mantem a narrativa. A eksperiensia desenvolve-se komo uma historia de kombustao lenta: o bot faz perguntas, deixa pistas e reduz a lista de sospeksos. Os administradores podem kontrolar a frekuensia destes eventos e estabeleker manualmente um alvo se kiserem dirigir a historia numa partikular.

---

### Music Controller (MC)

Reproduzao de musika praktika em kanais de voz do Diskord. Totalmente integrado — nao e necesaria konfigurakao para komekar a usa-lo.

Podes pedir ao bot ke reproduza kankoes ou URLs, akresentar pistas a uma kola e ver ke vem a seguir. Manuseia a reproduzao de YouTube, inkluindo a logika de reintento kuando o akseso esta restrikto. Kuando o kanal de voz esta vazio durante um tempo konfigurado, o deskonekta-se automatikamente para manter tudo ordenado. A eksperiensia e simples: solisitas, o bot reproduz.

---

## Canvas — Konfigurakao Interativa

Canvas e uma interface guiada kom botoes, menus despregaveis e vistas estruturadas. Forneske uma forma mais navegavel de interagir kom o bot komparado kom komandos brutos.

Abre Canvas kom `!canvas`. Si o teu servidor tem multiplos bots, podes dirigir-te a um espeksifiko: `!canvas <nome_bot>`.

Atraves de Canvas podes:

- Navegar e konfigurar roles
- Gerir konfigurakao pessoal (sukripoes, preferensias)
- Administrar komportamento a nivel de servidor (so administradores)
- Mudar a personalidade ativa e o idioma do teu servidor

---

## Komandos Gerais

Podes akeder a um menu de ajuda ke mostra todas as opkoes disponiveis, verifikar ke o bot esta a responder e reseber esta guia diretamente por MD para referensia futura. Tambem ha um komando para ver a identidade atual do bot — ke personalidade e idioma estao ativos no servidor. Para uma interakao ludika kom o personagem, podes pedir ao bot um insulto entregue no seu estilo.

---

## Kontroles de Administrador

Os administradores tem kontrol adisional sobre o komportamento do bot:

- **Personalidade e idioma** — mudar ke personagem enkarna o bot e ke idioma usa no servidor
- **Apelido** — estabeleker um nome de visibilizakao personalizado para o bot
- **Saudos** — ativar ou desativar MDs automatikos kuando os utilizadores se konektam
- **Mensagens de boas-vindas** — ativar ou desativar saudos para novos membros do servidor
- **Ativakao de roles** — ativar ou desativar roles espeksifikos (News Watcher, Treasure Hunter, etc.)
- **Komentarios** — kontrolar si o bot faz komentarios impulsionados pelo personagem sobre as suas atividades

Estes kontroles estao disponiveis tanto atraves de komandos komo atraves da interface Canvas.

---

## Fadiga e Limites de Taxa

O bot tem um sistema de protekao inkorporado para evitar o uso eksessivo. Si alkankas o limite para a tua sessao (rajada, por hora ou diario), o bot far-te-a saber kom uma mensagem amigavel em vez de khamar a IA. As primeiras solisitakoes do dia sao sempre permitidas komo periodo de graka.

---

## Publiko vs. Privado

**Em kanais do servidor**, o bot komporta-se komo um ator komunitario visivel. Esta konsiente ke esta num espako partilhado, responde a menkoes e reakiona a eventos do servidor.

**Em MDs**, a eksperiensia e mais direta. Alertas, verifikakoes de saldo, gestao de sukripoes e fluxos de konfigurakao pessoal funksionam melhor em mensagens privadas.

Uma regra simples: o servidor e sosial, os MDs sao pessoais.

---

## Memoria e Kontinuidade

O bot mantem varias kapas de konteksto por servidor:

- **Dialogo rezente** — a janela de konversa atual
- **Memoria reziente** — um resumo rolante de atividade reziente, atualizado kada poukas oras
- **Memoria diaria** — uma sintese kurta do dia do servidor, atualizada kada 24 oras
- **Memoria de relakao** — um resumo por utilizador atualizado kada hora, kapturando komo o bot perkebe a kada pessoa kom o tempo

E por isso ke o bot pode parecer komo se lembra de koisas. Nao rekupera registros kompletos — leva uma imagem sintetizada ke evolui kontinuamente.

---

## Termos e Lisensa

Antes de usar o RoleAgentBot, revisa os arquivos [LICENSE](../../LICENSE) e [TERMS_OF_SERVICE.md](../../TERMS_OF_SERVICE.md).

Pontos khave:

- Gratuito para uso nao komersial
- O uso komersial rekere konsentimento eskrito previo
- O software esta em desenvolvimento ativo — usa-lo sob o teu proprio risco
- Destinado a utilizadores adultos (18+)
- Nao rekomiendado para pessoas kom kondikoes de saude mental
- Aplikam konsiderakoes de privakidade a todas as konversas prosessadas por LLM
