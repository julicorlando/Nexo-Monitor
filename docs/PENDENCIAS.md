# Pendências e limites atuais

Este documento separa funções não implementadas de configuração e homologação. Não representa promessa de compatibilidade universal.

## Funções ainda não implementadas
- Descoberta de equipamentos por faixa de IP com aprovação antes de cadastrar.
- Topologia visual/mapa de unidades: dependências já existem, mas não há mapa renderizado.
- Incidentes com reconhecimento, responsável, prioridade e histórico de observações.
- Relatórios mensais/exportação, SLA por tempo, duração de quedas e tempo de recuperação. A disponibilidade atual é por amostras recebidas; ausência de dados não conta como uptime.
- Tráfego por segundo, erros de portas e tradução de MIBs específicas de PoE, toner e REP. SNMP atual consulta OID/subárvore; MikroTik mostra contadores cumulativos.
- Clientes, estatísticas e qualidade Wi-Fi UniFi. O conector atual lista dispositivos com paginação limitada.
- API proprietária Intelbras e comprovação de gravação recente Intelbras/Hikvision. Hikvision atual lê status de discos compatíveis.
- Instalador do coletor e registro automático como serviço Windows/Linux; execução e Docker estão disponíveis.
- Backup automático integrado e alertas de falha/restauração: há instruções, não um mecanismo implementado na aplicação.
- QR para cadastro TOTP e códigos de recuperação MFA; existe chave manual e reset administrativo.
- Atualização automática do coletor e configuração de certificados/credenciais pelo painel: segredos são configurados localmente.
- Confirmação de entrega/leitura WhatsApp por webhook; sucesso atual representa aceitação pelo gateway. Pode haver duplicação após timeout de envio.
- Agendamento recorrente de manutenção e regras de alertas por severidade/horário. Há manutenção com data final por equipamento.
- Retenção configurável e paginação completa dos históricos/painéis extensos. Alguns resultados usam limites fixos documentados.

## Dependem de informação e acesso aos equipamentos
- Modelos/firmwares de switches, APs, gravadores, REP e impressoras.
- Versão e endpoint da API UniFi, usuários de leitura MikroTik/Hikvision, MIBs/OIDs e documentação Intelbras.
- OIDs específicos não são adivinhados, e processo ativo/porta aberta não comprova operação comercial completa.

## Instalação e homologação pendentes
- DNS/HTTPS/NAT e deploy no Coolify.
- Coletores reais por unidade/servidor, relógios sincronizados, execução contínua e firewall.
- Pareamento WhatsApp e entrega real somente ao número cadastrado; SMTP real se usado.
- Validar coleta e limites no R230/Windows/Linux, perda do link, reenvio offline e dependências.
- Backups externos e teste de restauração isolado.
- Instalar monitor externo em outra rede: o script existe, mas o R230 não pode avisar por seu próprio gateway durante uma queda total.
- Testar build Docker, volume de sessão WAHA e reinício no ambiente real. Os testes locais não substituem homologação em PostgreSQL com concorrência nem teste de carga.

## Já implementado
Inventário e cadastros no painel, usuários por unidade, tipos de verificação, histórico, incidentes automáticos, manutenção, dependências, fila offline idempotente, alertas de equipamento/coletor, SMTP, WhatsApp/QR com único destino, auditoria, MFA TOTP, Docker Compose e guia de primeira configuração. Detalhes e limites nos guias de operação/integração/WhatsApp.
