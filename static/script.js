let directUrl = '';

async function resolveLink() {
    const urlInput = document.getElementById('teraboxUrl');
    const useBrowser = document.getElementById('useBrowser').checked;
    const teraboxUrl = urlInput.value.trim();

    // Validate URL
    if (!teraboxUrl) {
        showError('Please enter a TeraBox URL');
        return;
    }

    if (!isValidTeraBoxUrl(teraboxUrl)) {
        showError('Please enter a valid TeraBox share URL');
        return;
    }

    // Show loading state
    hideAll();
    document.getElementById('loading').classList.remove('hidden');
    document.getElementById('resolveBtn').disabled = true;

    try {
        const response = await fetch('/resolve', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                url: teraboxUrl,
                use_browser: useBrowser,
                timeout_seconds: 30
            })
        });

        const data = await response.json();

        if (response.ok) {
            showResult(data);
        } else {
            showError(data.detail || 'Failed to resolve the link. Please try again.');
        }
    } catch (error) {
        console.error('Error:', error);
        showError('Network error. Please check your connection and try again.');
    } finally {
        document.getElementById('resolveBtn').disabled = false;
    }
}

function showResult(data) {
    hideAll();
    
    directUrl = data.direct_url;
    
    // Set filename
    const filename = data.filename || extractFilenameFromUrl(data.direct_url) || 'Unknown';
    document.getElementById('filename').textContent = filename;
    
    // Set filesize
    const filesize = data.content_length ? formatBytes(data.content_length) : 'Unknown';
    document.getElementById('filesize').textContent = filesize;
    
    // Set file type
    const filetype = data.content_type || 'Unknown';
    document.getElementById('filetype').textContent = filetype;
    
    // Set download button
    document.getElementById('downloadBtn').href = data.direct_url;
    
    document.getElementById('result').classList.remove('hidden');
}

function showError(message) {
    hideAll();
    document.getElementById('errorMessage').textContent = message;
    document.getElementById('error').classList.remove('hidden');
}

function hideAll() {
    document.getElementById('loading').classList.add('hidden');
    document.getElementById('result').classList.add('hidden');
    document.getElementById('error').classList.add('hidden');
}

function reset() {
    hideAll();
    document.getElementById('teraboxUrl').value = '';
    document.getElementById('teraboxUrl').focus();
}

async function copyToClipboard() {
    try {
        await navigator.clipboard.writeText(directUrl);
        
        // Visual feedback
        const btn = event.target.closest('button');
        const originalText = btn.innerHTML;
        btn.innerHTML = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none"><path d="M20 6L9 17L4 12" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg> Copied!';
        btn.style.background = 'var(--success)';
        
        setTimeout(() => {
            btn.innerHTML = originalText;
            btn.style.background = '';
        }, 2000);
    } catch (error) {
        alert('Failed to copy to clipboard');
    }
}

function isValidTeraBoxUrl(url) {
    const patterns = [
        /terabox\.com/i,
        /1024tera\.com/i,
        /teraboxapp\.com/i,
        /4funbox\.com/i,
        /mirrobox\.com/i,
        /momerybox\.com/i,
        /teraboxlink\.com/i
    ];
    
    return patterns.some(pattern => pattern.test(url));
}

function formatBytes(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round((bytes / Math.pow(k, i)) * 100) / 100 + ' ' + sizes[i];
}

function extractFilenameFromUrl(url) {
    try {
        const urlObj = new URL(url);
        const pathname = urlObj.pathname;
        const parts = pathname.split('/');
        return parts[parts.length - 1] || null;
    } catch {
        return null;
    }
}

// Handle Enter key press
document.getElementById('teraboxUrl').addEventListener('keypress', function(event) {
    if (event.key === 'Enter') {
        resolveLink();
    }
});

// Auto-focus input on load
window.addEventListener('load', function() {
    document.getElementById('teraboxUrl').focus();
});
