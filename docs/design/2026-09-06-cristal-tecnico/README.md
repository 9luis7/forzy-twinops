# Cristal técnico — referência e validação visual

Artefatos preservados em 6 de setembro de 2026 para permitir a recuperação do acabamento visual em outro computador. O relatório completo está em [design-qa.md](../../../design-qa.md).

## Referência escolhida

[Proposta Cristal técnico](concept-cristal-tecnico.png) é uma imagem gerada para orientar hierarquia, superfícies e identidade. O equipamento ilustrado e os valores da proposta não são prova de funcionamento ou leituras reais. A implementação mantém o visualizador CAD e seus vínculos de sensores existentes.

A marca utilizada no produto está em [public/brand/twinops-symbol.png](../../../public/brand/twinops-symbol.png). Referência e marca mantêm os metadados de procedência da geração. Nenhuma imagem foi redesenhada ou recomprimida durante esta preservação.

## Capturas da implementação

Todas as capturas abaixo são da validação local com fixtures de teste, sem ingestão ou chamadas reais de IA. As vistas de página mostram esse aviso no topo; recortes e o diálogo móvel podem não incluir o aviso. Uma resposta com aparência de sucesso nesta coleção é uma resposta de fixture, não evidência de validação do provedor.

| Artefato | O que documenta |
| --- | --- |
| [Desktop final](premium-desktop-final.jpg) | Sensores acima do CAD, atualização acessível e copiloto aberto. Viewport de 1487 × 1058 CSS pixels. |
| [Marca](premium-brand-detail.jpg) | Recorte da navegação, símbolo e assinatura by FORZY. |
| [Visão geral no celular](premium-mobile-overview.jpg) | Coluna de sensores e botão do copiloto. Viewport de 390 × 844. |
| [Chat no celular](premium-mobile-chat.jpg) | Diálogo e estado de assistente indisponível, no viewport de 390 × 844. |
| [Tablet](premium-tablet.jpg) | Conteúdo com espaço reservado ao copiloto, no viewport de 900 × 900. Inclui estado de indisponibilidade. |
| [Resposta de fixture](premium-chat-answer.jpg) | Resposta compacta e fontes, limites e detalhes recolhidos. Não houve consulta real ao modelo. |

As capturas foram fornecidas com extensão `.png`, mas contêm JPEG. As cópias versionadas usam a extensão `.jpg` correspondente ao formato real; seus bytes foram preservados. O tamanho físico da captura pode omitir a área da barra de rolagem do viewport.

## Integridade e recuperação

[SHA256SUMS.txt](SHA256SUMS.txt) registra os hashes dos sete artefatos e da marca usada pelo app. Os caminhos do manifesto são relativos à raiz do repositório. A cópia foi comparada com os arquivos de origem antes de ser entregue para commit.

Este diretório contém apenas documentação e imagens revisadas. As entradas locais de QA, fixtures auxiliares, caches, variáveis de ambiente e bancos não fazem parte do arquivo. O aplicativo continua usando sua entrada normal e seus gateways existentes. Instale as dependências declaradas no projeto para recompilar; a integração com a API e o resultado da publicação devem ser verificados separadamente das capturas visuais.
