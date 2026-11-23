# Progress

Atualizar quando fechares algo relevante. Quem abre um chat novo cola este ficheiro.

## Estado atual
- Tracker com janelas de 5s e features novas (episódios de correção, intervalos, pausas, rato): reescrito, testado com dados simulados, falta testar no PC
- Servidor guarda janelas de 5s e agrega a 15 min em `features.py`: feito, testado com dados simulados
- Wearables (Apple Watch, Whoop, Garmin, Amazfit) e Oura (sono): endpoints e scripts existentes, por validar com dados reais
- Check-in de energia e foco (1 a 5): página `/checkin` feita, falta usar durante 1 semana
- Gráficos `/explore`: feitos, falta ver com dados reais

## Decisões
- Biometria só do sono no MVP, previsão do pico (não adaptativa)
- Sem conteúdo de texto, só timing
- Totais por janela, agregação somando totais (sem médias de médias)
- Episódios de correção em vez de contagem de backspaces
- Normalização por utilizador fica para a fase de modelo

## Próximos passos
- [ ] Rodar segredos da Oura e do token da API, limpar o histórico do repo
- [ ] Testar o tracker no PC e correr 1 semana
- [ ] Pôr o `/checkin` no ecrã inicial do telemóvel e responder a cada 60 a 90 min
- [ ] Criar o atalho do Apple Watch (ver `APPLE_WATCH.md`) e testar com o endpoint `/api/biometrics/apple-watch-raw` (feito e testado no servidor, falta testar o atalho no iPhone)
- [ ] Decidir normalização por utilizador (baseline rolante)

## Em aberto
- Teste curto de reação/escrita como segunda label
- Onde guardar os dados a longo prazo (SQLite no Render apaga ao reiniciar sem disco persistente)

## Log
- 2026-11-23: revisão do repo, tracker e agregação reescritos.
