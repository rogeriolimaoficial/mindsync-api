# Apple Watch: atalho que envia o sono

O atalho lê o sono, o HRV e a frequência cardíaca em repouso da app Saúde e envia ao servidor. O servidor faz as contas (fases do sono, sobreposições, médias).

**Pré-requisitos:** Apple Watch com a app Sono ligada (Saúde > Sono) e a dormir com o relógio posto. Servidor atualizado (`git push`) e deploy Live no Render.

Os nomes das ações estão em inglês. Se o iPhone estiver em português, procura na barra de pesquisa de ações pelo nome em inglês ou por parte do nome em português.

## Criar o atalho "MindSync Sono"

Atalhos > **+** (novo atalho) > nome: `MindSync Sono`.

**Bloco 1: sono**
1. **Find Health Samples**. Filtros: *Type* **é** *Sleep*; *Start Date* **está nos últimos** *1 day*. Ordenar por *Start Date*, mais antigo primeiro. Sem limite.
2. **Repeat with Each** (item de Health Samples). Dentro:
   - **Format Date**: *Start Date* do item, formato **ISO 8601**.
   - **Format Date**: *End Date* do item, formato **ISO 8601**.
   - **Text**: `Valor|Início|Fim`, ou seja: o *Value* do item, o carácter `|`, a primeira data formatada, `|`, a segunda data formatada.
3. **End Repeat**.
4. **Combine Text**: *Repeat Results*, separador **New Lines**. Chama à variável `sono`.

**Bloco 2: HRV**
5. **Find Health Samples**: *Type* **é** *Heart Rate Variability*; *Start Date* nos últimos *1 day*.
6. **Repeat with Each**, dentro um **Text** só com o *Value* do item. **End Repeat**.
7. **Combine Text** (*New Lines*). Variável `hrv`.

**Bloco 3: frequência cardíaca em repouso**
8. **Find Health Samples**: *Type* **é** *Resting Heart Rate*; *Start Date* nos últimos *1 day*.
9. **Repeat with Each**, dentro um **Text** só com o *Value* do item. **End Repeat**.
10. **Combine Text** (*New Lines*). Variável `fc`.

**Envio**
11. **Get Contents of URL**
    - URL: `https://mindsync-api.onrender.com/api/biometrics/apple-watch-raw`
    - Método: **POST**
    - Cabeçalhos: `Authorization` = `Bearer O_TEU_TOKEN` (a palavra *Bearer*, um espaço e o token)
    - Corpo do pedido: **JSON**, com 4 campos de texto:
      - `user_id` = `rogerio`
      - `sleep_lines` = variável `sono`
      - `hrv_values` = variável `hrv`
      - `resting_hr` = variável `fc`
12. **Show Result** (só para testar).

## Testar
Toca no atalho de manhã, depois de acordares, com o iPhone desbloqueado. A primeira vez o iPhone pede permissão para ler dados de Saúde: aceita (Sono, HRV, Frequência cardíaca em repouso).

Se correr bem, aparece algo como `"status":"success"` com minutos de sono por fase. Se aparecer um erro ou `fases_desconhecidas`, tira um screenshot e manda.

## Usar no dia a dia
Os dados de Saúde ficam encriptados com o iPhone bloqueado, por isso uma automação a uma hora fixa pode falhar. O mais fiável é pôr o atalho no ecrã inicial (partilhar > Adicionar ao ecrã principal) e tocar nele depois de acordar. Depois de funcionar uma semana, podes experimentar uma automação (Atalhos > Automação > *Alarm* > *Is Stopped* > correr o atalho).
