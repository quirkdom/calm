class Calm < Formula
  include Language::Python::Virtualenv

  desc "Terminal-native CLI assistant backed by a local calmd daemon"
  homepage "https://github.com/quirkdom/calm"
  url "https://files.pythonhosted.org/packages/39/de/dfaf2e958426fb5f261dddb8d15506c4701cf56d00ec941f700f47131489/calm_cli-0.3.0.tar.gz"
  sha256 "1f08a3f66360d7c0e1f782c4242c60a1b57b6c8e3b35bb1d5a5ad7eb85fc4cb8"
  license "MIT"

  depends_on :macos
  depends_on arch: :arm64
  depends_on "python@3.14"
  depends_on "rust" => :build
  depends_on "maturin" => :build

  resource "annotated-doc" do
    url "https://files.pythonhosted.org/packages/57/ba/046ceea27344560984e26a590f90bc7f4a75b06701f653222458922b558c/annotated_doc-0.0.4.tar.gz"
    sha256 "fbcda96e87e9c92ad167c2e53839e57503ecfda18804ea28102353485033faa4"
  end

  resource "anyio" do
    url "https://files.pythonhosted.org/packages/96/f0/5eb65b2bb0d09ac6776f2eb54adee6abe8228ea05b20a5ad0e4945de8aac/anyio-4.12.1.tar.gz"
    sha256 "41cfcc3a4c85d3f05c932da7c26d0201ac36f72abd4435ba90d0464a3ffed703"
  end

  resource "certifi" do
    url "https://files.pythonhosted.org/packages/af/2d/7bf41579a8986e348fa033a31cdd0e4121114f6bce2457e8876010b092dd/certifi-2026.2.25.tar.gz"
    sha256 "e887ab5cee78ea814d3472169153c2d12cd43b14bd03329a39a9c6e2e80bfba7"
  end

  resource "click" do
    url "https://files.pythonhosted.org/packages/3d/fa/656b739db8587d7b5dfa22e22ed02566950fbfbcdc20311993483657a5c0/click-8.3.1.tar.gz"
    sha256 "12ff4785d337a1bb490bb7e9c2b1ee5da3112e94a8622f26a6c77f5d2fc6842a"
  end

  resource "filelock" do
    url "https://files.pythonhosted.org/packages/94/b8/00651a0f559862f3bb7d6f7477b192afe3f583cc5e26403b44e59a55ab34/filelock-3.25.2.tar.gz"
    sha256 "b64ece2b38f4ca29dd3e810287aa8c48182bbecd1ae6e9ae126c9b35f1382694"
  end

  resource "fsspec" do
    url "https://files.pythonhosted.org/packages/51/7c/f60c259dcbf4f0c47cc4ddb8f7720d2dcdc8888c8e5ad84c73ea4531cc5b/fsspec-2026.2.0.tar.gz"
    sha256 "6544e34b16869f5aacd5b90bdf1a71acb37792ea3ddf6125ee69a22a53fb8bff"
  end

  resource "h11" do
    url "https://files.pythonhosted.org/packages/01/ee/02a2c011bdab74c6fb3c75474d40b3052059d95df7e73351460c8588d963/h11-0.16.0.tar.gz"
    sha256 "4e35b956cf45792e4caa5885e69fba00bdbc6ffafbfa020300e549b208ee5ff1"
  end

  resource "hf-xet" do
    url "https://files.pythonhosted.org/packages/64/2e/af4475c32b4378b0e92a587adb1aa3ec53e3450fd3e5fe0372a874531c00/hf_xet-1.4.2-cp37-abi3-macosx_11_0_arm64.whl"
    sha256 "e9b38d876e94d4bdcf650778d6ebbaa791dd28de08db9736c43faff06ede1b5a"
  end

  resource "httpcore" do
    url "https://files.pythonhosted.org/packages/06/94/82699a10bca87a5556c9c59b5963f2d039dbd239f25bc2a63907a05a14cb/httpcore-1.0.9.tar.gz"
    sha256 "6e34463af53fd2ab5d807f399a9b45ea31c3dfa2276f15a2c3f00afff6e176e8"
  end

  resource "httpx" do
    url "https://files.pythonhosted.org/packages/b1/df/48c586a5fe32a0f01324ee087459e112ebb7224f646c0b5023f5e79e9956/httpx-0.28.1.tar.gz"
    sha256 "75e98c5f16b0f35b567856f597f06ff2270a374470a5c2392242528e3e3e42fc"
  end

  resource "huggingface-hub" do
    url "https://files.pythonhosted.org/packages/b4/a8/94ccc0aec97b996a3a68f3e1fa06a4bd7185dd02bf22bfba794a0ade8440/huggingface_hub-1.7.1.tar.gz"
    sha256 "be38fe66e9b03c027ad755cb9e4b87ff0303c98acf515b5d579690beb0bf3048"
  end

  resource "idna" do
    url "https://files.pythonhosted.org/packages/6f/6d/0703ccc57f3a7233505399edb88de3cbd678da106337b9fcde432b65ed60/idna-3.11.tar.gz"
    sha256 "795dafcc9c04ed0c1fb032c2aa73654d8e8c5023a7df64a53f39190ada629902"
  end

  resource "Jinja2" do
    url "https://files.pythonhosted.org/packages/df/bf/f7da0350254c0ed7c72f3e33cef02e048281fec7ecec5f032d4aac52226b/jinja2-3.1.6.tar.gz"
    sha256 "0137fb05990d35f1275a587e9aee6d56da821fc83491a0fb838183be43f66d6d"
  end

  resource "markdown-it-py" do
    url "https://files.pythonhosted.org/packages/5b/f5/4ec618ed16cc4f8fb3b701563655a69816155e79e24a17b651541804721d/markdown_it_py-4.0.0.tar.gz"
    sha256 "cb0a2b4aa34f932c007117b194e945bd74e0ec24133ceb5bac59009cda1cb9f3"
  end

  resource "MarkupSafe" do
    url "https://files.pythonhosted.org/packages/7e/99/7690b6d4034fffd95959cbe0c02de8deb3098cc577c67bb6a24fe5d7caa7/markupsafe-3.0.3.tar.gz"
    sha256 "722695808f4b6457b320fdc131280796bdceb04ab50fe1795cd540799ebe1698"
  end

  resource "mdurl" do
    url "https://files.pythonhosted.org/packages/d6/54/cfe61301667036ec958cb99bd3efefba235e65cdeb9c84d24a8293ba1d90/mdurl-0.1.2.tar.gz"
    sha256 "bb413d29f5eea38f31dd4754dd7377d4465116fb207585f97bf925588687c1ba"
  end

  resource "mlx" do
    if MacOS.version >= 26
      url "https://files.pythonhosted.org/packages/e1/17/abec0bd0f9347dae13e60b33325cb199312798842901953495e19f3bb3c8/mlx-0.31.1-cp314-cp314-macosx_26_0_arm64.whl"
      sha256 "69bc88b41ddd61b44cd6a4d417790f9971ba3fdf58d824934cea95a95b9b4031"
    elsif MacOS.version >= :sequoia
      url "https://files.pythonhosted.org/packages/98/58/2d925cb3fa3cd28d279ed6f44508ab7fbbf7359b17359914aa3652a7d734/mlx-0.31.1-cp314-cp314-macosx_15_0_arm64.whl"
      sha256 "d90b0529b22553eb1353b113b7233aa391ca55e24b1ba69024c732fcc21c5c49"
    else
      url "https://files.pythonhosted.org/packages/99/65/208f511acd5fb1ed0b08f047bd6229583845cc6f4b5aa6547a3219332dbb/mlx-0.31.1-cp314-cp314-macosx_14_0_arm64.whl"
      sha256 "bba9d471ba20e050676292b1089a355c8042d3fc9462e4c1738a9735d7d40cfa"
    end
  end

  resource "mlx-lm" do
    url "https://files.pythonhosted.org/packages/9e/f9/3f5597c62bd5733ebb3c9f96c33f2065db16353d743b8548bb05a01b7dd3/mlx_lm-0.31.1.tar.gz"
    sha256 "1b2362ea301427004e5dda43b9241d751d4cb80eba641f6b85b29fc493affac5"
  end

  resource "mlx-metal" do
    if MacOS.version >= 26
      url "https://files.pythonhosted.org/packages/51/bc/987cb99e3aafb296aa11ce5133838a10eae8447edd53168d0804d4fb3a14/mlx_metal-0.31.1-py3-none-macosx_26_0_arm64.whl"
      sha256 "e7324b7c56b519ae67c025d3ced07e5d35bc3a9f19d4c45fe4927f385148c59e"
    elsif MacOS.version >= :sequoia
      url "https://files.pythonhosted.org/packages/c7/34/4c3c6890ce6095b2ab2ba2f5f15c9a7ba17208d47f8cacb572885a2dc0eb/mlx_metal-0.31.1-py3-none-macosx_15_0_arm64.whl"
      sha256 "6c56bd8cd27743e635f5a90a22535af7c31bd22b4b126d46b6da2da52d72e413"
    else
      url "https://files.pythonhosted.org/packages/39/66/2313497fdbc7fbadf8e026c09366e3f049f9114e65ca4edc23cdb8699186/mlx_metal-0.31.1-py3-none-macosx_14_0_arm64.whl"
      sha256 "70741174131dbf7fdd479cb730e06e08c358eac3bf7905d9e884e7960cfdd5b8"
    end
  end

  resource "numpy" do
    url "https://files.pythonhosted.org/packages/32/af/a7a39464e2c0a21526fb4fb76e346fb172ebc92f6d1c7a07c2c139cc17b1/numpy-2.4.3-cp314-cp314-macosx_14_0_arm64.whl"
    sha256 "a111698b4a3f8dcbe54c64a7708f049355abd603e619013c346553c1fd4ca90b"
  end

  resource "packaging" do
    url "https://files.pythonhosted.org/packages/65/ee/299d360cdc32edc7d2cf530f3accf79c4fca01e96ffc950d8a52213bd8e4/packaging-26.0.tar.gz"
    sha256 "00243ae351a257117b6a241061796684b084ed1c516a08c48a3f7e147a9d80b4"
  end

  resource "protobuf" do
    url "https://files.pythonhosted.org/packages/f2/00/04a2ab36b70a52d0356852979e08b44edde0435f2115dc66e25f2100f3ab/protobuf-7.34.0.tar.gz"
    sha256 "3871a3df67c710aaf7bb8d214cc997342e63ceebd940c8c7fc65c9b3d697591a"
  end

  resource "Pygments" do
    url "https://files.pythonhosted.org/packages/b0/77/a5b8c569bf593b0140bde72ea885a803b82086995367bf2037de0159d924/pygments-2.19.2.tar.gz"
    sha256 "636cb2477cec7f8952536970bc533bc43743542f70392ae026374600add5b887"
  end

  resource "PyYAML" do
    url "https://files.pythonhosted.org/packages/05/8e/961c0007c59b8dd7729d542c61a4d537767a59645b82a0b521206e1e25c2/pyyaml-6.0.3.tar.gz"
    sha256 "d76623373421df22fb4cf8817020cbb7ef15c725b9d5e45f17e189bfc384190f"
  end

  resource "regex" do
    url "https://files.pythonhosted.org/packages/8b/71/41455aa99a5a5ac1eaf311f5d8efd9ce6433c03ac1e0962de163350d0d97/regex-2026.2.28.tar.gz"
    sha256 "a729e47d418ea11d03469f321aaf67cdee8954cde3ff2cf8403ab87951ad10f2"
  end

  resource "rich" do
    url "https://files.pythonhosted.org/packages/b3/c6/f3b320c27991c46f43ee9d856302c70dc2d0fb2dba4842ff739d5f46b393/rich-14.3.3.tar.gz"
    sha256 "b8daa0b9e4eef54dd8cf7c86c03713f53241884e814f4e2f5fb342fe520f639b"
  end

  resource "safetensors" do
    url "https://files.pythonhosted.org/packages/e8/00/374c0c068e30cd31f1e1b46b4b5738168ec79e7689ca82ee93ddfea05109/safetensors-0.7.0-cp38-abi3-macosx_11_0_arm64.whl"
    sha256 "94fd4858284736bb67a897a41608b5b0c2496c9bdb3bf2af1fa3409127f20d57"
  end

  resource "sentencepiece" do
    url "https://files.pythonhosted.org/packages/ea/99/bbe054ebb5a5039457c590e0a4156ed073fb0fe9ce4f7523404dd5b37463/sentencepiece-0.2.1-cp314-cp314-macosx_11_0_arm64.whl"
    sha256 "c83b85ab2d6576607f31df77ff86f28182be4a8de6d175d2c33ca609925f5da1"
  end

  resource "shellingham" do
    url "https://files.pythonhosted.org/packages/58/15/8b3609fd3830ef7b27b655beb4b4e9c62313a4e8da8c676e142cc210d58e/shellingham-1.5.4.tar.gz"
    sha256 "8dbca0739d487e5bd35ab3ca4b36e11c4078f3a234bfce294b0a0291363404de"
  end

  resource "tokenizers" do
    url "https://files.pythonhosted.org/packages/2e/47/174dca0502ef88b28f1c9e06b73ce33500eedfac7a7692108aec220464e7/tokenizers-0.22.2-cp39-abi3-macosx_11_0_arm64.whl"
    sha256 "1e418a55456beedca4621dbab65a318981467a2b188e982a23e117f115ce5001"
  end

  resource "tqdm" do
    url "https://files.pythonhosted.org/packages/09/a9/6ba95a270c6f1fbcd8dac228323f2777d886cb206987444e4bce66338dd4/tqdm-4.67.3.tar.gz"
    sha256 "7d825f03f89244ef73f1d4ce193cb1774a8179fd96f31d7e1dcde62092b960bb"
  end

  resource "transformers" do
    url "https://files.pythonhosted.org/packages/fc/1a/70e830d53ecc96ce69cfa8de38f163712d2b43ac52fbd743f39f56025c31/transformers-5.3.0.tar.gz"
    sha256 "009555b364029da9e2946d41f1c5de9f15e6b1df46b189b7293f33a161b9c557"
  end

  resource "typer" do
    url "https://files.pythonhosted.org/packages/f5/24/cb09efec5cc954f7f9b930bf8279447d24618bb6758d4f6adf2574c41780/typer-0.24.1.tar.gz"
    sha256 "e39b4732d65fbdcde189ae76cf7cd48aeae72919dea1fdfc16593be016256b45"
  end

  resource "typing-extensions" do
    url "https://files.pythonhosted.org/packages/72/94/1a15dd82efb362ac84269196e94cf00f187f7ed21c242792a923cdb1c61f/typing_extensions-4.15.0.tar.gz"
    sha256 "0cea48d173cc12fa28ecabc3b837ea3cf6f38c6d1136f85cbaaf598984861466"
  end

  def install
    venv = virtualenv_create(libexec, "python3.14")

    # Process all resources
    resources.each do |r|
      if ["mlx", "mlx-metal", "hf-xet", "numpy", "safetensors", "sentencepiece", "tokenizers"].include?(r.name)
        # Pip is strict about wheel filenames.
        # Homebrew's cached_download has a hash prefix that pip rejects.
        # We symlink it to its original name in the buildpath.
        r.fetch
        wheel_name = r.url.split("/").last
        (buildpath/wheel_name).make_relative_symlink(r.cached_download)
        venv.pip_install buildpath/wheel_name
      else
        # Standard installation for source distributions
        venv.pip_install r
      end
    end

    # Install the main package and link binaries
    venv.pip_install_and_link buildpath
  end

  service do
    run [opt_bin/"calmd"]
    keep_alive false
    run_at_load true
    log_path var/"log/calmd.log"
    error_log_path var/"log/calmd.error.log"
  end

  test do
    assert_match "calm", shell_output("#{bin}/calm --help")
    assert_match "calmd", shell_output("#{bin}/calmd --help")
  end
end
