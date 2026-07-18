# Design — Frontend Sentinela CME: Login (acoplado à API real)

> Spec de implementação. Primeira fatia que sai do mock puro — a API de
> auth/meta da Fase 3 (`api/auth.py`, `api/meta.py`) já existe de verdade no
> backend (não só desenhada; testada, 154 testes no total do backend). Este
> slice acopla o **login** contra ela. `metaApi`/`historyApi`/`liveApi`
> continuam mockados — fora de escopo aqui.

## 1. Objetivo e escopo

Tela de login (`/login`) que autentica contra `POST /auth/login` (real),
guarda o JWT retornado, protege as rotas existentes (`/`, `/area/:code`,
`/sensor/:code`) atrás de um guard, e oferece logout.

**Confirmado rodando** (verificado com `curl` antes de desenhar isto):
`POST http://localhost:8001/auth/login` com `{usuario:"admin", senha:"admin"}`
devolve `{access_token: "<jwt>", token_type: "bearer"}`; senha errada → `401`.
CORS adicionado em `api/main.py` (liberado pras portas `5173-5179`, onde o
Vite dev sobe).

**Fora de escopo**: anexar o token nas chamadas de `metaApi`/`historyApi`/
`liveApi` (continuam mockadas, sem checar auth); filtragem multi-tenant
(a própria API ainda não filtra por `partner_id` nesta rodada);
usuário de serviço dedicado; "esqueci minha senha"/"lembrar-me".

## 2. Contrato (`frontend/CONTRACTS.md` ganha uma seção nova)

```ts
type AuthApi = {
  login(usuario: string, senha: string): Promise<{ access_token: string; token_type: string }>
}
```

Mapeamento real: `POST /auth/login`, body `{usuario, senha}` → resposta
exata acima; `401` em credencial inválida. **Não** devolve nome/partner_id
solto — esses claims ficam dentro do payload do JWT (`sub`, `partner_id`,
`exp`), opacos pro frontend (não precisamos decodificar pra exibir nada
nesta fatia, só pra checar expiração — ver §4).

## 3. Seam mock/real — reusa o padrão já existente

`authApi` ganha as duas implementações, seguindo exatamente o padrão de
`lib/api/index.ts`:

- `mockAuthApi`: aceita só `admin`/`admin` (mesma credencial de teste da API
  real — ensina a credencial certa pra quando testar de verdade). Gera um
  token **genuinamente formatado como JWT** (3 segmentos base64, payload
  `{sub, partner_id, exp}`, assinatura fake) — não porque alguém vá verificar
  a assinatura no mock, mas pra o decode de expiração (§4) funcionar
  idêntico pro mock e pro real, zero divergência de lógica.
- `realAuthApi`: `fetch(`${API_BASE_URL}/auth/login`, {...})`, erro em
  não-200.

Diferente de `metaApi`/`historyApi`/`liveApi` (que hoje sempre caem em mock
mesmo com `VITE_API_MODE=real`, com warning), `authApi` **tem** impl real
funcional agora — `VITE_API_MODE=real` ativa o real só pra auth, os outros
3 continuam mock (aviso no console ajustado pra refletir isso com precisão,
não mais "sem impl real ainda" genérico).

Nova env var: `VITE_API_BASE_URL` (default `http://localhost:8001` — porta
onde a API foi testada rodando nesta sessão). `.env.local` (não versionado)
guarda `VITE_API_MODE=real` pra testar contra a API de verdade nesta
máquina; `.env`/default do repo continua `mock` (sem depender de a API
estar de pé pra rodar o frontend).

## 4. Estado de auth — Context + localStorage, sem lib nova

Sem Zustand (nem outra lib de estado global) — o projeto todo até aqui usou
só hooks/Context, e isso é pouco estado (`token`, `isAuthenticated`). Segue
o mesmo minimalismo.

- `lib/jwt.ts` — `decodeJwtExp(token: string): number | null`, puro: decodifica
  o segundo segmento (payload) do JWT em base64, lê `exp` (segundos Unix),
  devolve em ms. **Não verifica assinatura** — isso é responsabilidade do
  servidor a cada request; o decode client-side é só pra saber quando
  encerrar a sessão localmente, não é um controle de segurança.
- `lib/useAuth.tsx` — `AuthProvider` + `useAuth()`. Guarda `{token}` em
  `localStorage` (chave `sentinela_token`). No mount, lê do storage; se
  `decodeJwtExp` indicar expirado, limpa e trata como deslogado. Expõe
  `login(usuario, senha)` (chama `authApi.login`, guarda o token, lança erro
  se falhar — a UI mostra) e `logout()` (limpa storage + estado).

## 5. Rotas e guard

```tsx
<Routes>
  <Route path="/login" element={<LoginPage />} />
  <Route element={<AuthGuard />}>
    <Route path="/" element={<OverviewPage />} />
    <Route path="/area/:areaCode" element={<AreaPage />} />
    <Route path="/sensor/:code" element={<SensorRoute />} />
  </Route>
</Routes>
```

`AuthGuard` (rota-pai com `<Outlet/>`): se `useAuth().isAuthenticated`,
renderiza `<Outlet/>`; senão, `<Navigate to="/login" replace />`.
`AuthProvider` envolve `<App/>` em `main.tsx` (fica disponível em toda rota,
incluindo `/login`).

## 6. Componentes

- `LoginPage` — campos usuário/senha, botão "Entrar" (estado de loading),
  erro inline ("Usuário ou senha inválidos") em credencial errada. Sucesso
  → `navigate('/')`.
- Botão de logout — ao lado do `ThemeToggle` nas 3 páginas já existentes
  (mesmo padrão de consistência da fatia de Overview: todas as páginas
  autenticadas mostram o mesmo cabeçalho de ações).

## 7. Testes

1. `decodeJwtExp`: token válido devolve `exp` correto; token expirado
   detectável (comparar com "agora"); token malformado devolve `null`, não
   lança.
2. `mockAuthApi`: `admin`/`admin` devolve token JWT-shaped com `exp` ~1h no
   futuro; credencial errada rejeita.
3. `useAuth`/`AuthProvider`: login guarda token e vira `isAuthenticated`;
   logout limpa; mount com token expirado no storage já nasce deslogado.
4. `AuthGuard`: sem auth → redireciona pra `/login`; com auth → renderiza
   filhos.
5. `LoginPage`: submit com credencial certa navega pra `/`; credencial
   errada mostra erro, não navega.
6. Integração: `/` sem login redireciona pra `/login`; login bem-sucedido
   entra na Overview; logout volta pra `/login` e tentar acessar `/` nesse
   estado redireciona de novo.

## 8. Entregáveis

- `lib/jwt.ts`, `lib/useAuth.tsx`.
- `lib/api/mock/authApi.ts` + `lib/api/real/authApi.ts`.
- `lib/api/contracts.ts` ganha `AuthApi`; `lib/api/index.ts` seleciona por
  `VITE_API_MODE`.
- `components/LoginPage.tsx` (ou `pages/`), `components/AuthGuard.tsx`,
  `components/LogoutButton.tsx`.
- `App.tsx`/`main.tsx` com guard + provider.
- `frontend/CONTRACTS.md` ganha a seção `AuthApi`.
- `.env.local` (não versionado) configurado pra testar contra a API real
  já rodando nesta sessão (`localhost:8001`).
- Suite verde; verificação visual real (login de verdade contra a API,
  não só o mock) — mesma disciplina de toda fatia anterior.
