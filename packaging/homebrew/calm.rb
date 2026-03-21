class Calm < Formula
  include Language::Python::Virtualenv

  desc "Terminal-native CLI assistant backed by a local calmd daemon"
  homepage "https://github.com/quirkdom/calm"
  url "https://files.pythonhosted.org/packages/c0/84/7e7c968a6aa0e10f0eaa58d18c163fe33e278fc4de46f196811b3551b230/calm_cli-0.4.0.tar.gz"
  sha256 "7dc7878d1cc2144017ac397b3648390a1d1e3c833d441c5e734e3e1ef03af8c6"
  license "MIT"

  depends_on arch: :arm64
  depends_on :macos
  depends_on "python@3.14"

  on_macos do

    resource "hf-xet" do
      url "https://files.pythonhosted.org/packages/e4/71/b99aed3823c9d1795e4865cf437d651097356a3f38c7d5877e4ac544b8e4/hf_xet-1.3.2-cp37-abi3-macosx_11_0_arm64.whl"
      sha256 "a85d3d43743174393afe27835bde0cd146e652b5fcfdbcd624602daef2ef3259"
    end

    resource "mlx" do
      if MacOS.version >= 26
        url "https://files.pythonhosted.org/packages/63/5a/81cf057dbc005a43d27b7dfaff88198c61bbfe76cb8da3499821083c3fca/mlx-0.31.0-cp314-cp314-macosx_26_0_arm64.whl"
        sha256 "d2014d113070846c6cdee980653f561c92a4a663a449f64e70c15bbf74d637e1"
      elsif MacOS.version >= :sequoia
        url "https://files.pythonhosted.org/packages/e3/6b/70f0a254d7ace58a030547a99219f1342c3cf383029e1af90eee3efaeb85/mlx-0.31.0-cp314-cp314-macosx_15_0_arm64.whl"
        sha256 "ba330fe40d73b202880bbb5cac62de0b639cf4c44a12853bcadb34a9e3ffe880"
      else
        url "https://files.pythonhosted.org/packages/66/60/0152a44ed737c3b16e9044909d01212b99e216c6ab4b2f76faa054ae8172/mlx-0.31.0-cp314-cp314-macosx_14_0_arm64.whl"
        sha256 "cce3e15cf11c608c9e721502fe56e54f9f48b897e9b80f1204a48643d68710c0"
      end
    end

    resource "mlx-metal" do
      if MacOS.version >= 26
        url "https://files.pythonhosted.org/packages/ed/8f/cdaffd759b4c71e74c294e773daacad8aafabac103b93e0aa56d4468d279/mlx_metal-0.31.0-py3-none-macosx_26_0_arm64.whl"
        sha256 "7fd412f55ddf9f1d90c2cd86ce281d19e8eb93d093c6dbd784a49f8bd7d0a22c"
      elsif MacOS.version >= :sequoia
        url "https://files.pythonhosted.org/packages/8d/42/c6d7bfd097b777f932d6cf8c79e41b565070b63cc452a069b8804e505140/mlx_metal-0.31.0-py3-none-macosx_15_0_arm64.whl"
        sha256 "554dc7cb29e0ea5fb6941df42f11a1de385b095848e6183c7a99d7c1f1a11f5d"
      else
        url "https://files.pythonhosted.org/packages/94/4f/0a0671dfa62b59bf429edab0e2c9c7f9bc77865aa4218cd46f2f41d7d11a/mlx_metal-0.31.0-py3-none-macosx_14_0_arm64.whl"
        sha256 "1c572a6e3634a63060c103b0c38ac309e2d217be15519e3d8f0d6b452bb015f5"
      end
    end

    resource "numpy" do
      url "https://files.pythonhosted.org/packages/fb/0b/f9e49ba6c923678ad5bc38181c08ac5e53b7a5754dbca8e581aa1a56b1ff/numpy-2.4.2-cp314-cp314-macosx_14_0_arm64.whl"
      sha256 "7cdde6de52fb6664b00b056341265441192d1291c130e99183ec0d4b110ff8b1"
    end

    resource "safetensors" do
      url "https://files.pythonhosted.org/packages/e8/00/374c0c068e30cd31f1e1b46b4b5738168ec79e7689ca82ee93ddfea05109/safetensors-0.7.0-cp38-abi3-macosx_11_0_arm64.whl"
      sha256 "94fd4858284736bb67a897a41608b5b0c2496c9bdb3bf2af1fa3409127f20d57"
    end

    resource "sentencepiece" do
      url "https://files.pythonhosted.org/packages/ea/99/bbe054ebb5a5039457c590e0a4156ed073fb0fe9ce4f7523404dd5b37463/sentencepiece-0.2.1-cp314-cp314-macosx_11_0_arm64.whl"
      sha256 "c83b85ab2d6576607f31df77ff86f28182be4a8de6d175d2c33ca609925f5da1"
    end

    resource "tokenizers" do
      url "https://files.pythonhosted.org/packages/2e/47/174dca0502ef88b28f1c9e06b73ce33500eedfac7a7692108aec220464e7/tokenizers-0.22.2-cp39-abi3-macosx_11_0_arm64.whl"
      sha256 "1e418a55456beedca4621dbab65a318981467a2b188e982a23e117f115ce5001"
    end

  end

  resource "calm-cli" do
    url "https://files.pythonhosted.org/packages/79/e7/b87defc6eede03800dacfa502dee8816d316cb5197e8e1e10366350f5e61/calm_cli-0.4.0-py3-none-any.whl"
    sha256 "b7672980e8a39637c0d26db91647199ece50c2f7a1c7f8aea32387aa946720c8"
  end

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
    url "https://files.pythonhosted.org/packages/77/18/a1fd2231c679dcb9726204645721b12498aeac28e1ad0601038f94b42556/filelock-3.25.0.tar.gz"
    sha256 "8f00faf3abf9dc730a1ffe9c354ae5c04e079ab7d3a683b7c32da5dd05f26af3"
  end

  resource "fsspec" do
    url "https://files.pythonhosted.org/packages/51/7c/f60c259dcbf4f0c47cc4ddb8f7720d2dcdc8888c8e5ad84c73ea4531cc5b/fsspec-2026.2.0.tar.gz"
    sha256 "6544e34b16869f5aacd5b90bdf1a71acb37792ea3ddf6125ee69a22a53fb8bff"
  end

  resource "h11" do
    url "https://files.pythonhosted.org/packages/01/ee/02a2c011bdab74c6fb3c75474d40b3052059d95df7e73351460c8588d963/h11-0.16.0.tar.gz"
    sha256 "4e35b956cf45792e4caa5885e69fba00bdbc6ffafbfa020300e549b208ee5ff1"
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
    url "https://files.pythonhosted.org/packages/ae/76/b5efb3033d8499b17f9386beaf60f64c461798e1ee16d10bc9c0077beba5/huggingface_hub-1.5.0.tar.gz"
    sha256 "f281838db29265880fb543de7a23b0f81d3504675de82044307ea3c6c62f799d"
  end

  resource "idna" do
    url "https://files.pythonhosted.org/packages/6f/6d/0703ccc57f3a7233505399edb88de3cbd678da106337b9fcde432b65ed60/idna-3.11.tar.gz"
    sha256 "795dafcc9c04ed0c1fb032c2aa73654d8e8c5023a7df64a53f39190ada629902"
  end

  resource "jinja2" do
    url "https://files.pythonhosted.org/packages/df/bf/f7da0350254c0ed7c72f3e33cef02e048281fec7ecec5f032d4aac52226b/jinja2-3.1.6.tar.gz"
    sha256 "0137fb05990d35f1275a587e9aee6d56da821fc83491a0fb838183be43f66d6d"
  end

  resource "markdown-it-py" do
    url "https://files.pythonhosted.org/packages/5b/f5/4ec618ed16cc4f8fb3b701563655a69816155e79e24a17b651541804721d/markdown_it_py-4.0.0.tar.gz"
    sha256 "cb0a2b4aa34f932c007117b194e945bd74e0ec24133ceb5bac59009cda1cb9f3"
  end

  resource "markupsafe" do
    url "https://files.pythonhosted.org/packages/7e/99/7690b6d4034fffd95959cbe0c02de8deb3098cc577c67bb6a24fe5d7caa7/markupsafe-3.0.3.tar.gz"
    sha256 "722695808f4b6457b320fdc131280796bdceb04ab50fe1795cd540799ebe1698"
  end

  resource "mdurl" do
    url "https://files.pythonhosted.org/packages/d6/54/cfe61301667036ec958cb99bd3efefba235e65cdeb9c84d24a8293ba1d90/mdurl-0.1.2.tar.gz"
    sha256 "bb413d29f5eea38f31dd4754dd7377d4465116fb207585f97bf925588687c1ba"
  end

  resource "mlx-lm" do
    url "https://files.pythonhosted.org/packages/9e/f9/3f5597c62bd5733ebb3c9f96c33f2065db16353d743b8548bb05a01b7dd3/mlx_lm-0.31.1.tar.gz"
    sha256 "1b2362ea301427004e5dda43b9241d751d4cb80eba641f6b85b29fc493affac5"
  end

  resource "packaging" do
    url "https://files.pythonhosted.org/packages/65/ee/299d360cdc32edc7d2cf530f3accf79c4fca01e96ffc950d8a52213bd8e4/packaging-26.0.tar.gz"
    sha256 "00243ae351a257117b6a241061796684b084ed1c516a08c48a3f7e147a9d80b4"
  end

  resource "protobuf" do
    url "https://files.pythonhosted.org/packages/f2/00/04a2ab36b70a52d0356852979e08b44edde0435f2115dc66e25f2100f3ab/protobuf-7.34.0.tar.gz"
    sha256 "3871a3df67c710aaf7bb8d214cc997342e63ceebd940c8c7fc65c9b3d697591a"
  end

  resource "pygments" do
    url "https://files.pythonhosted.org/packages/b0/77/a5b8c569bf593b0140bde72ea885a803b82086995367bf2037de0159d924/pygments-2.19.2.tar.gz"
    sha256 "636cb2477cec7f8952536970bc533bc43743542f70392ae026374600add5b887"
  end

  resource "pyyaml" do
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

  resource "shellingham" do
    url "https://files.pythonhosted.org/packages/58/15/8b3609fd3830ef7b27b655beb4b4e9c62313a4e8da8c676e142cc210d58e/shellingham-1.5.4.tar.gz"
    sha256 "8dbca0739d487e5bd35ab3ca4b36e11c4078f3a234bfce294b0a0291363404de"
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

    resources.each do |r|
      next if r.name == "calm-cli"

      if r.url.end_with?(".whl")
        r.fetch
        wheel_name = File.basename(r.url.split("#").first)
        (buildpath/wheel_name).make_relative_symlink(r.cached_download)
        venv.pip_install buildpath/wheel_name
      else
        venv.pip_install r
      end
    end

    main_res = resource("calm-cli")
    main_res.fetch
    main_wheel = File.basename(main_res.url.split("#").first)
    (buildpath/main_wheel).make_relative_symlink(main_res.cached_download)
    venv.pip_install buildpath/main_wheel

    bin.install_symlink libexec/"bin/calm"
    bin.install_symlink libexec/"bin/calmd"
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
