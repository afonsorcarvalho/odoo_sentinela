from hub import identidade_ssh


def test_cria_par_e_pubkey_openssh(tmp_path):
    caminho = tmp_path / "ssh_hub"
    chave = identidade_ssh.carregar_ou_criar_chave_ssh(caminho)
    assert caminho.exists()
    assert caminho.with_suffix(".pub").exists()
    pub = identidade_ssh.pubkey_openssh(chave)
    assert pub.startswith("ssh-ed25519 ")


def test_idempotente_recarrega_mesma_chave(tmp_path):
    caminho = tmp_path / "ssh_hub"
    a = identidade_ssh.carregar_ou_criar_chave_ssh(caminho)
    b = identidade_ssh.carregar_ou_criar_chave_ssh(caminho)
    assert identidade_ssh.pubkey_openssh(a) == identidade_ssh.pubkey_openssh(b)
