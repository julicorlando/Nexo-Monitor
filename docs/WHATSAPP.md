# WhatsApp de alertas com QR code

## Instalação no Coolify
1. Selecione `compose.whatsapp.yaml` em vez de `compose.yaml`. Ele inclui web, worker, PostgreSQL e gateway WAHA com volume persistente de sessão.
2. Configure as variáveis usuais e gere WAHA_API_KEY forte. WAHA_IMAGE pode fixar a tag/digest da versão homologada; o padrão usa a imagem pública devlikeapro/waha:latest e deve ser homologado no deploy.
3. Associe domínio somente ao serviço web (porta 8000). WAHA permanece interno, sem porta pública, sem Dashboard/Swagger público.
4. Entre como superusuário e abra WhatsApp. Cadastre **um único** número com país + DDD + número, ex.: formato 55DDDNÚMERO; ative os alertas e salve.
5. Clique Conectar/retomar. No celular, WhatsApp → Aparelhos conectados → Conectar aparelho; leia o QR exibido. A tela consulta estado/QR a cada 15 segundos. Quando WORKING, a sessão está conectada.
6. Clique Enviar teste ao número cadastrado e acompanhe o histórico. O worker envia o teste; nada é enviado durante a implementação ou antes de você configurar o canal.

## Restrição de destinatário
Existe uma configuração global, com um único número. O worker monta chatId a partir dela; não aceita destino, texto livre, grupo ou lista do navegador. Mudanças são restritas a superusuário e auditadas. Formulário aceita telefone formatado e salva apenas os dígitos. A API do gateway fica privada e a chave apenas nas variáveis dos serviços web/worker. Pessoas com acesso ao host ou à chave do WAHA podem usar o gateway diretamente; a restrição do Nexo é aplicada pela aplicação, não pelo WhatsApp.

## Alertas
Por padrão envia falha de equipamento e perda de coletor. Recuperações são opcionais. Regras de dependência, manutenção e falhas consecutivas já são aplicadas antes de gerar notificações. Ativar ou alterar o destinatário inicia um novo período de alertas: não dispara todo o histórico anterior. Falhas já recuperadas ou suprimidas antes do envio são marcadas event_resolved e não são enviadas como alerta atual.

Cada mensagem contém evento, unidade, detalhes, data e ID do registro. Até seis tentativas com espera crescente. Envio e erros são registrados independentemente do e-mail. Se o número for alterado, eventos iniciados no número anterior não são redirecionados. Na tela pode solicitar nova tentativa de um evento elegível para o mesmo número; isso não permite editar destinatário/texto. O teste manual tem intervalo mínimo de um minuto.

Uma resposta de sucesso da API indica aceitação pelo gateway, não comprova leitura pelo destinatário. Se ocorrer timeout após envio antes de salvar a confirmação, uma nova tentativa pode repetir a mensagem; o ID no texto ajuda a identificar. WhatsApp Web/WAHA é um serviço independente da Cloud API oficial e pode exigir novo pareamento. Mantenha e-mail e monitor externo como canais complementares. Se o R230/internet da matriz cair, este gateway local também fica indisponível.

## Gateway externo já existente
Com o compose básico, configure WAHA_URL/WAHA_API_KEY tanto no web quanto no worker e use um gateway acessível em rede privada ou HTTPS. O backend não aceita URL/chave pelo formulário. Com o compose integrado, a URL já é http://waha:3000 na rede Docker privada.

## Referências e homologação
APIs usadas: GET /api/sessions/default, POST /api/sessions, POST /api/sessions/default/start|restart|stop, GET /api/default/auth/qr e POST /api/sendText.
Documentação primária: https://waha.devlike.pro/docs/how-to/sessions/ e https://waha.devlike.pro/docs/how-to/send-messages/.

Testes automatizados usam gateway simulado e verificam destino único, bloqueio de grupos, permissões, QR sem cache e retentativa. Pareamento, envio real e persistência da sessão após restart precisam ser testados no PowerEdge/Coolify.
