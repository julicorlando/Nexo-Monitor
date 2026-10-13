# Instalação e operação

## Coolify
Use a branch main e compose.yaml. Configure as variáveis de .env.example, domínio HTTPS no serviço web/8000 e disco persistente do PostgreSQL. Não associe domínio ao worker ou banco. O worker precisa de uma réplica apenas. Crie o superusuário pelo terminal do serviço web. Migrations rodam antes do Gunicorn; worker espera healthcheck web.

## Coletores
Para métricas do host, execute Python nativamente. Linux precisa de ping/net-snmp, Windows precisa de Python e psutil; SNMP exige instalação de net-snmp compatível. Configure NEXO_URL, NEXO_TOKEN e opcionalmente NEXO_SPOOL_PATH. Execute `python collector/agent.py` como serviço com reinício. Um único processo por arquivo SQLite. O diretório da fila precisa ser gravável e persistente. No Docker use collector/compose.yaml. Configure as variáveis de integração no serviço do coletor: não as envie ao painel.

A fila guarda até seis dias e 10.000 lotes, descartando os antigos se atingir o limite. Configuração é mantida em cache. Reenvio usa UUID por lote e horário UTC; lotes inválidos (equipamento removido/desativado) são descartados com registro em log. Sincronize os relógios com NTP. O estado atual não é sobrescrito por uma amostra mais antiga. Receber amostras históricas não comprova funcionamento atual. Não haverá fila histórica antes de iniciar o coletor.

## Dependências e manutenção
Configure equipamento pai no inventário (ex.: roteador principal). Falhas do dependente ficam registradas; seu alerta é suprimido enquanto o pai está sem confirmação ou indisponível. Incidentes suprimidos são fechados sem alerta de recuperação. Use manutenção até uma data/hora para silenciar alertas do equipamento. A regra é avaliada a cada lote e pelo worker para equipamentos com dados recentes. Não altera a coleta.

## MFA
Em Segurança, adicione manualmente a chave TOTP a um autenticador e confirme com senha/código. A chave armazenada é criptografada usando SECRET_KEY; preserve essa chave nos backups. Login público e login do Django Admin exigem código quando ativo. Sessões anteriores são encerradas ao acessar telas protegidas após a ativação. Recuperação: `python manage.py reset_mfa USUARIO` no terminal autorizado. Reative o MFA após recuperar. Não há códigos de recuperação nem QR nesta versão.

## Backup PostgreSQL
No host, adapte os nomes dos containers obtidos no Coolify. Execute um dump com `docker exec CONTAINER_DB pg_dump -U nexo -Fc nexo > nexo-backup.dump`. Guarde também SECRET_KEY e as variáveis de integração em um cofre separado e copie os backups para outro servidor. Não versione dumps ou segredos. Teste a restauração em ambiente isolado usando `pg_restore -U nexo -d nexo --clean --if-exists` com o arquivo transferido ao container; pare web/worker antes de restaurar uma base em uso. Defina retenção e agendamento no host/Coolify. Backup e restauração não foram executados no R230.

## Monitor independente
Rode collector/external_probe.py em outra máquina/rede, apontando NEXO_EXTERNAL_URL para https://dominio/health/. Configure SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM e SMTP_TO. O script avisa mudança de estado; exige STARTTLS. Inicialização também envia estado atual. Não foi instalado em servidor externo nesta entrega.

## Homologação na rede real
- Validar DNS/HTTPS/login/MFA no celular e computador.
- Comparar um equipamento online/offline com estado observado.
- Interromper internet do coletor, conferir fila, retornar e verificar histórico sem duplicação.
- Derrubar roteador pai e conferir agrupamento.
- Testar manutenção, destinatários e e-mail de recuperação.
- Confirmar leitura de métricas e serviços em cada SO.
- Validar APIs e versões dos fabricantes e restaurar um backup isolado.
