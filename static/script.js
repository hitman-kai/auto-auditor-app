// static/script.js

window.addEventListener('load', () => {
    let walletPublicKey = null;
    const reportContentEl = document.getElementById('report-content');
    const connectBtn = document.getElementById('connectBtn');
    const disconnectBtn = document.getElementById('disconnectBtn');
    const scannerSection = document.getElementById('scannerSection');
    const walletConnector = document.getElementById('wallet-connector');
    const walletAddressEl = document.getElementById('walletAddress');
    const downloadCardBtn = document.getElementById('downloadCardBtn');
    const shareTwitterBtn = document.getElementById('shareTwitterBtn');
    const themeToggleBtn = document.getElementById('themeToggleBtn');
    
    if (!reportContentEl || !downloadCardBtn || !shareTwitterBtn || !themeToggleBtn) {
        console.error('Critical elements not found');
        return;
    }

    downloadCardBtn.style.display = 'none';
    shareTwitterBtn.style.display = 'none';
    
    function setTheme(theme) {
        document.documentElement.setAttribute('data-theme', theme);
        localStorage.setItem('theme', theme);
        themeToggleBtn.textContent = theme === 'dark' ? '?? Light Mode' : '?? Dark Mode';
    }
    const savedTheme = localStorage.getItem('theme') || 'light';
    setTheme(savedTheme);

    themeToggleBtn.addEventListener('click', () => {
        const currentTheme = document.documentElement.getAttribute('data-theme') || 'light';
        const newTheme = currentTheme === 'light' ? 'dark' : 'light';
        setTheme(newTheme);
    });

    function ensureVisibility() {
        reportContentEl.style.display = 'block';
        downloadCardBtn.style.display = 'inline-block';
        shareTwitterBtn.style.display = 'inline-block';
    }

    const getProvider = () => {
        if ('phantom' in window) {
            const provider = window.phantom?.solana;
            if (provider && provider.isPhantom) return provider;
        }
        connectBtn.innerText = "Install Phantom";
        connectBtn.onclick = () => window.open('https://phantom.app/', '_blank');
        return null;
    };

    const provider = getProvider();
    if (provider) {
        provider.on('connect', (publicKey) => handleConnect(publicKey.toBase58()));
        provider.on('disconnect', handleDisconnect);
        provider.connect({ onlyIfTrusted: true }).catch((err) => connectBtn.innerText = "Connect Wallet");
        connectBtn.addEventListener('click', async () => { try { await provider.connect(); } catch (err) { alert('Failed to connect wallet.'); } });
        disconnectBtn.addEventListener('click', async () => { try { await provider.disconnect(); } catch (err) { console.error('Disconnect error:', err); } });
    }

    function handleConnect(publicKeyString) {
        walletPublicKey = publicKeyString;
        walletConnector.style.display = 'none';
        scannerSection.style.display = 'block';
        walletAddressEl.innerText = `${publicKeyString.substring(0, 4)}...${publicKeyString.substring(publicKeyString.length - 4)}`;
    }

    function handleDisconnect() {
        walletPublicKey = null;
        walletConnector.style.display = 'block';
        scannerSection.style.display = 'none';
        reportContentEl.innerHTML = '';
        downloadCardBtn.style.display = 'none';
        shareTwitterBtn.style.display = 'none';
    }

    async function performScan() {
        const tokenAddress = document.getElementById('tokenAddressInput').value;
        if (!tokenAddress || !walletPublicKey) {
            alert('Please connect wallet and enter a token address.');
            return;
        }
        document.getElementById('loading').style.display = 'block';
        reportContentEl.innerHTML = '';
        reportContentEl.style.display = 'block';
        downloadCardBtn.style.display = 'none';
        shareTwitterBtn.style.display = 'none';
        try {
            const response = await fetch('/analyze', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ user_wallet: walletPublicKey, token_address: tokenAddress })
            });
            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.error || `HTTP error! Status: ${response.status}`);
            }
            const data = await response.json();
            document.getElementById('loading').style.display = 'none';
            reportContentEl.innerHTML = data.report || '<div class="report-container card"><p>No report data.</p></div>';
            ensureVisibility();
        } catch (error) {
            reportContentEl.innerHTML = `<div class="report-container card"><p style="color: red;">Scan failed: ${error.message}</p></div>`;
            alert(`Scan failed: ${error.message}`);
        } finally {
            document.getElementById('loading').style.display = 'none';
        }
    }
    document.getElementById('scanBtn').addEventListener('click', performScan);

    downloadCardBtn.addEventListener('click', async () => {
        const reportDiv = document.querySelector('.report-container');
        if (!reportDiv) {
            alert('No report on screen to generate a card from.');
            return;
        }
        
        const name = reportDiv.querySelector('h2').textContent.replace('Token Report: ', '').split(' (')[0];
        const symbol = reportDiv.querySelector('h2').textContent.match(/\(([^)]+)\)/)?.[1] || 'N/A';
        
        function getValueFromList(labelText) {
            const strongElements = reportDiv.querySelectorAll('li strong');
            for (let strongEl of strongElements) {
                if (strongEl.textContent.includes(labelText)) {
                    const valueSpan = strongEl.nextElementSibling;
                    if (valueSpan && valueSpan.classList.contains('value')) return valueSpan.textContent.trim();
                }
            }
            return 'N/A';
        }

        const fdv = getValueFromList("Market Cap (FDV)");
        const scoreText = reportDiv.querySelector('h3').textContent;
        const degenScore = (scoreText.match(/⬜/g) || []).length;
        
        const originalBtnText = downloadCardBtn.textContent;
        downloadCardBtn.textContent = '?? Generating Card...';
        downloadCardBtn.disabled = true;

        try {
            const response = await fetch('/generate_ai_card', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name, symbol, fdv, degen_score: degenScore })
            });
            
            if (!response.ok) {
                const errorData = await response.json().catch(() => null);
                throw new Error(errorData?.error || 'Server failed to generate the card.');
            }

            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.style.display = 'none';
            a.href = url;
            
            const contentDisposition = response.headers.get('content-disposition');
            let filename = `${symbol.replace('$', '')}_degen_card.png`;
            if (contentDisposition && contentDisposition.includes('attachment')) {
                const filenameMatch = contentDisposition.match(/filename="(.+)"/);
                if (filenameMatch && filenameMatch[1]) {
                  filename = filenameMatch[1];
                }
            }
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            a.remove();
        } catch (error) {
            alert(`Error: ${error.message}`);
        } finally {
            downloadCardBtn.textContent = originalBtnText;
            downloadCardBtn.disabled = false;
        }
    });

    shareTwitterBtn.addEventListener('click', () => {
        const reportDiv = document.querySelector('.report-container');
        if (!reportDiv) { return; }
        const name = reportDiv.querySelector('h2').textContent.replace('Token Report: ', '').split(' (')[0];
        const symbol = reportDiv.querySelector('h2').textContent.match(/\(([^)]+)\)/)?.[1] || 'N/A';
        const tweetText = `Check out my Degen Report Card for ${name} (${symbol})! Scanned with @retardedauditor #Solana #MemeCoin`;
        const twitterUrl = `https://x.com/intent/tweet?text=${encodeURIComponent(tweetText)}`;
        window.open(twitterUrl, '_blank');
    });

    reportContentEl.addEventListener('click', (event) => {
        if (event.target && event.target.id === 'refreshBtn') performScan();
    });
});
