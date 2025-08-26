let videoSystem = null;
let spectatorVideoSystem = null;
let sessionId = null;
let currentQuizId = null;
let hasAnswered = false;
const baseUrl = window.location.origin;
const socket = io(baseUrl, {
    path: '/socket.io',
    transports: ['websocket'],
    reconnectionAttempts: 10,
    reconnectionDelay: 1000
});

function initApp() {
    videoSystem = initVideoPlayer('video-player');
    spectatorVideoSystem = initVideoPlayer('spectator-video');
    checkCurrentSession();
}

function checkCurrentSession() {
    fetch(`${baseUrl}/api/sessions/current`)
        .then(response => {
            if (!response.ok) {
                console.error('Erreur API session:', response.status);
                document.getElementById('response').innerText = 'Aucune session en direct';
                return null;
            }
            return response.json();
        })
        .then(data => {
            if (data && data.id) {
                if (sessionId !== data.id) {
                    sessionId = data.id;
                    socket.emit('join_session', { session_id: sessionId });
                    if (videoSystem) {
                        const hlsUrl = `https://agri.visiotech.me/live/${data.stream_key}.m3u8`;
                        loadHlsVideo(hlsUrl, videoSystem);
                    }
                    fetchQuizzes(data.id);
                }
            } else {
                sessionId = null;
                document.getElementById('response').innerText = 'Aucune session en direct';
                stopHlsVideo(videoSystem);
            }
        })
        .catch(error => {
            console.error('Erreur API:', error);
            document.getElementById('response').innerText = 'Erreur de connexion au serveur: ' + error.message;
        });
}

function hasQuizBeenAnswered(quizId) {
    const answeredQuizzes = JSON.parse(localStorage.getItem('answeredQuizzes') || '[]');
    return answeredQuizzes.includes(quizId);
}

function markQuizAsAnswered(quizId) {
    const answeredQuizzes = JSON.parse(localStorage.getItem('answeredQuizzes') || '[]');
    if (!answeredQuizzes.includes(quizId)) {
        answeredQuizzes.push(quizId);
        localStorage.setItem('answeredQuizzes', JSON.stringify(answeredQuizzes));
    }
}

function removeQuizFromAnswered(quizId) {
    const answeredQuizzes = JSON.parse(localStorage.getItem('answeredQuizzes') || '[]');
    const updatedQuizzes = answeredQuizzes.filter(id => id !== quizId);
    localStorage.setItem('answeredQuizzes', JSON.stringify(updatedQuizzes));
}

function initVideoPlayer(elementId) {
    const videoPlayer = document.getElementById(elementId);
    if (videoPlayer.canPlayType('application/vnd.apple.mpegurl')) {
        console.log('Support HLS natif détecté');
        return { player: videoPlayer, isNative: true };
    } else if (Hls.isSupported()) {
        console.log('Utilisation de hls.js version:', Hls.version);
        const hls = new Hls({
            debug: true,
            enableWorker: false,
            lowLatencyMode: true,
            maxBufferSize: 10 * 1000 * 1000,
            maxBufferLength: 10,
            liveSyncDurationCount: 2,
            liveMaxLatencyDurationCount: 4,
            startFragPrefetch: true,
            autoStartLoad: true,
            maxFragLookUpTolerance: 0.1,
            backBufferLength: 0
        });
        return { player: videoPlayer, hls: hls, isNative: false };
    } else {
        console.error('Aucun support HLS détecté');
        document.getElementById('response').innerText = 'Votre appareil ne supporte pas la lecture HLS';
        return null;
    }
}

function stopHlsVideo(videoSystem) {
    if (!videoSystem) return;
    if (videoSystem.isNative) {
        videoSystem.player.src = '';
        videoSystem.player.load();
    } else if (videoSystem.hls) {
        videoSystem.hls.stopLoad();
        videoSystem.hls.detachMedia();
        videoSystem.hls.destroy();
        videoSystem.hls = new Hls({
            debug: true,
            enableWorker: false,
            lowLatencyMode: true,
            maxBufferSize: 10 * 1000 * 1000,
            maxBufferLength: 10,
            liveSyncDurationCount: 2,
            liveMaxLatencyDurationCount: 4,
            startFragPrefetch: true,
            autoStartLoad: true,
            maxFragLookUpTolerance: 0.1,
            backBufferLength: 0,
            xhrSetup: function(xhr, url) {
                xhr.withCredentials = false;
            }
        });
    }
    videoSystem.player.pause();
}

async function checkStreamAvailability(hlsUrl, maxAttempts = 20, interval = 2000) {
    console.log(`Vérification de la disponibilité du flux: ${hlsUrl}`);
    for (let attempt = 1; attempt <= maxAttempts; attempt++) {
        try {
            let response;
            if (typeof fetch === 'function') {
                response = await fetch(hlsUrl, { method: 'HEAD', cache: 'no-store' });
            } else {
                response = await new Promise((resolve, reject) => {
                    const xhr = new XMLHttpRequest();
                    xhr.open('HEAD', hlsUrl, true);
                    xhr.onload = () => resolve({ ok: xhr.status >= 200 && xhr.status < 300 });
                    xhr.onerror = () => reject(new Error('Erreur réseau'));
                    xhr.send();
                });
            }
            if (response.ok) {
                console.log(`Flux disponible après ${attempt} tentative(s)`);
                return true;
            }
            console.log(`Flux non disponible (tentative ${attempt}/${maxAttempts})`);
        } catch (error) {
            console.error(`Erreur lors de la vérification (tentative ${attempt}/${maxAttempts}):`, error);
        }
        await new Promise(resolve => setTimeout(resolve, interval));
    }
    console.error(`Échec après ${maxAttempts} tentatives`);
    return false;
}

function loadHlsVideo(hlsUrl, videoSystem) {
    console.log(`Chargement du flux HLS: ${hlsUrl}`);
    if (!videoSystem) {
        console.error('Système vidéo non initialisé');
        document.getElementById('response').innerText = 'Erreur: Système vidéo non initialisé';
        return;
    }

    hlsUrl = hlsUrl.replace('http://', 'https://');

    const loadingMessage = document.getElementById('spectator-loading');
    if (loadingMessage) {
        loadingMessage.style.display = 'flex';
    }

    checkStreamAvailability(hlsUrl).then(isAvailable => {
        if (!isAvailable) {
            console.error('Flux HLS non disponible après plusieurs tentatives');
            document.getElementById('response').innerText = 'Le flux n\'est pas disponible. Veuillez réessayer plus tard.';
            if (loadingMessage) {
                loadingMessage.style.display = 'none';
            }
            return;
        }

        if (videoSystem.isNative) {
            videoSystem.player.src = hlsUrl;
            videoSystem.player.load();
            videoSystem.player.play().catch(e => {
                console.error('Erreur de lecture native:', e);
                document.getElementById('response').innerText = 'Erreur de lecture du flux HLS: ' + e.message;
                if (loadingMessage) {
                    loadingMessage.style.display = 'none';
                }
            });
        } else {
            videoSystem.hls.loadSource(hlsUrl);
            videoSystem.hls.attachMedia(videoSystem.player);
            videoSystem.hls.on(Hls.Events.MANIFEST_PARSED, () => {
                console.log('Manifeste HLS chargé');
                if (loadingMessage) {
                    loadingMessage.style.display = 'none';
                }
                videoSystem.player.play().catch(e => {
                    console.error('Erreur de lecture hls.js:', e);
                    document.getElementById('response').innerText = 'Erreur de lecture du flux HLS: ' + e.message;
                });
            });
            videoSystem.hls.on(Hls.Events.ERROR, (event, data) => {
                console.error('Erreur hls.js:', data);
                document.getElementById('response').innerText = `Erreur HLS: ${data.type} - ${data.details}`;
                if (data.fatal) {
                    console.error('Erreur fatale, nouvelle tentative de vérification du flux...');
                    if (loadingMessage) {
                        loadingMessage.style.display = 'flex';
                    }
                    stopHlsVideo(videoSystem);
                    loadHlsVideo(hlsUrl, videoSystem);
                }
            });
        }
    });
}

function seekToLive() {
    if (videoSystem && !videoSystem.isNative) {
        videoSystem.hls.liveSyncPosition = videoSystem.hls.latency || 0;
        videoSystem.hls.startLoad();
        videoSystem.player.play().catch(e => {
            console.error('Erreur lors du retour en direct:', e);
            document.getElementById('response').innerText = 'Erreur lors du retour en direct: ' + e.message;
        });
    }
}

document.addEventListener('DOMContentLoaded', function() {
    socket.on('connect', () => {
        console.log('WebSocket connecté');
        document.getElementById('response').innerText = 'Connecté au serveur';
        checkCurrentSession();
    });

    socket.on('connect_error', (error) => {
        console.error('Erreur de connexion WebSocket:', error);
        document.getElementById('response').innerText = 'Erreur de connexion WebSocket: ' + error.message;
    });

    socket.on('disconnect', () => {
        console.log('WebSocket déconnecté');
        document.getElementById('response').innerText = 'WebSocket déconnecté';
    });

    socket.on('toggle_qr_code', (data) => {
        const qrContainer = document.getElementById('qr-container');
        const qrImage = document.getElementById('qr-code');
        const qrLink = document.getElementById('qr-link');

        if (data.show) {
            fetch(`/api/queue/${data.session_id}/qr`)
                .then(response => response.json())
                .then(data => {
                    qrImage.src = data.qr_code;
                    qrLink.href = data.link;
                    qrLink.textContent = data.link;
                    qrContainer.style.display = 'block';
                });
        } else {
            qrContainer.style.display = 'none';
            qrImage.src = '';
            qrLink.href = '#';
            qrLink.textContent = '';
        }
    });

    socket.on('spectator_approved', (data) => {
        console.log('Spectator approuvé:', data);
        const spectatorVideoContainer = document.getElementById('spectator-video-container');
        spectatorVideoContainer.style.display = 'block';
        const hlsUrl = `https://agri.visiotech.me/live/${data.stream_key}.m3u8`;
        stopHlsVideo(spectatorVideoSystem);
        loadHlsVideo(hlsUrl, spectatorVideoSystem);
    });

    socket.on('spectator_stream_stopped', (data) => {
        console.log('Flux du spectateur arrêté:', data);
        stopHlsVideo(spectatorVideoSystem);
        document.getElementById('spectator-video-container').style.display = 'none';
        const loadingMessage = document.getElementById('spectator-loading');
        if (loadingMessage) {
            loadingMessage.style.display = 'none';
        }
    });

    socket.on('new_question', (data) => {
        const questionsDiv = document.getElementById('questions-list');
        const questionHtml = `
            <div class="card mb-2 question-slide">
                <div class="card-body">
                    <p><strong>Question :</strong> ${data.question_text}</p>
                    <small class="text-muted">(${new Date(data.timestamp).toLocaleString('fr-FR', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' })})</small>
                    ${data.answer_text ? `<p><strong>Réponse :</strong> ${data.answer_text}</p>` : ''}
                </div>
            </div>
        `;
        questionsDiv.insertAdjacentHTML('beforeend', questionHtml);
    });

    socket.on('new_answer', (data) => {
        const questionsDiv = document.getElementById('questions-list');
        const questionElements = questionsDiv.querySelectorAll('.card-body');
        questionElements.forEach(element => {
            if (element.textContent.includes(data.question_text)) {
                const answerHtml = `<p><strong>Réponse :</strong> ${data.answer_text}</p>`;
                element.insertAdjacentHTML('beforeend', answerHtml);
            }
        });
    });

    socket.on('new_quiz', (data) => {
        hasAnswered = hasQuizBeenAnswered(data.id);
        document.getElementById('quiz-question').innerText = data.question;
        const optionsList = document.getElementById('quiz-options');
        optionsList.innerHTML = '';
        data.options.forEach((option, index) => {
            const li = document.createElement('li');
            li.innerText = option;
            li.tabIndex = hasAnswered ? -1 : 0;
            li.className = 'quiz-option' + (hasAnswered ? ' disabled' : '');
            li.dataset.index = index;
            if (!hasAnswered) {
                li.onclick = () => sendQuizResponse(data.id, index);
                li.onkeypress = (e) => {
                    if (e.key === 'Enter') sendQuizResponse(data.id, index);
                };
            }
            optionsList.appendChild(li);
        });
        currentQuizId = data.id;
        if (hasAnswered) {
            socket.emit('request_quiz_result', { quiz_id: data.id });
        }
    });

    socket.on('new_quiz_response', (data) => {
        if (data.quiz_id === currentQuizId && hasAnswered) {
            const optionsList = document.getElementById('quiz-options');
            const options = optionsList.querySelectorAll('.quiz-option');
            options.forEach(option => {
                const index = parseInt(option.dataset.index);
                if (index === data.correct_option) {
                    option.classList.add('correct');
                    option.innerHTML = `<i class="fa-solid fa-check"></i> ${option.innerText}`;
                } else if (index === data.selected_option) {
                    option.classList.add('incorrect');
                    option.innerHTML = `<i class="fa-solid fa-times"></i> ${option.innerText}`;
                }
                option.classList.add('disabled');
                option.tabIndex = -1;
                option.onclick = null;
                option.onkeypress = null;
            });
            document.getElementById('response').innerText = 'Résultat affiché !';
        }
    });

    socket.on('quiz_deleted', (data) => {
        if (data.quiz_id === currentQuizId) {
            document.getElementById('quiz-question').innerText = '';
            document.getElementById('quiz-options').innerHTML = '';
            document.getElementById('response').innerText = 'Quiz supprimé';
            hasAnswered = false;
            currentQuizId = null;
            removeQuizFromAnswered(data.quiz_id);
        }
    });

    socket.on('quiz_result', (data) => {
        if (data.quiz_id === currentQuizId) {
            const optionsList = document.getElementById('quiz-options');
            const options = optionsList.querySelectorAll('.quiz-option');
            options.forEach(option => {
                const index = parseInt(option.dataset.index);
                if (index === data.correct_option) {
                    option.classList.add('correct');
                    option.innerHTML = `<i class="fa-solid fa-check"></i> ${option.innerText}`;
                } else if (index === data.selected_option) {
                    option.classList.add('incorrect');
                    option.innerHTML = `<i class="fa-solid fa-times"></i> ${option.innerText}`;
                }
                option.classList.add('disabled');
                option.tabIndex = -1;
                option.onclick = null;
                option.onkeypress = null;
            });
            document.getElementById('response').innerText = 'Résultat affiché !';
        }
    });

    function fetchQuizzes(id) {
        fetch(`${baseUrl}/api/sessions/${id}/quizzes`)
            .then(response => {
                if (!response.ok) {
                    console.error('Erreur API quizzes:', response.status);
                    document.getElementById('response').innerText = 'Aucun quiz disponible';
                    return [];
                }
                return response.json();
            })
            .then(quizzes => {
                if (quizzes.length > 0) {
                    const quiz = quizzes[quizzes.length - 1];
                    hasAnswered = hasQuizBeenAnswered(quiz.id);
                    document.getElementById('quiz-question').innerText = quiz.question;
                    const optionsList = document.getElementById('quiz-options');
                    optionsList.innerHTML = '';
                    quiz.options.forEach((option, index) => {
                        const li = document.createElement('li');
                        li.innerText = option;
                        li.tabIndex = hasAnswered ? -1 : 0;
                        li.className = 'quiz-option' + (hasAnswered ? ' disabled' : '');
                        li.dataset.index = index;
                        if (!hasAnswered) {
                            li.onclick = () => sendQuizResponse(quiz.id, index);
                            li.onkeypress = (e) => {
                                if (e.key === 'Enter') sendQuizResponse(quiz.id, index);
                            };
                        }
                        optionsList.appendChild(li);
                    });
                    currentQuizId = quiz.id;
                    if (hasAnswered) {
                        socket.emit('request_quiz_result', { quiz_id: quiz.id });
                    }
                } else {
                    document.getElementById('response').innerText = 'Aucun quiz disponible';
                }
            })
            .catch(error => {
                console.error('Erreur quizzes:', error);
                document.getElementById('response').innerText = 'Erreur lors du chargement des quizzes: ' + error.message;
            });
    }

    function sendQuestion() {
        const questionInput = document.getElementById('question-input').value;
        if (questionInput && sessionId) {
            socket.emit('question', {
                session_id: sessionId,
                question_text: questionInput
            });
            document.getElementById('question-input').value = '';
            document.getElementById('response').innerText = 'Question envoyée !';
        }
    }

    function sendQuizResponse(quizId, selectedOption) {
        if (sessionId && !hasAnswered) {
            socket.emit('quiz_response', {
                session_id: sessionId,
                quiz_id: quizId,
                selected_option: selectedOption
            });
            hasAnswered = true;
            markQuizAsAnswered(quizId);
            document.getElementById('response').innerText = 'Réponse envoyée !';
        } else if (hasAnswered) {
            document.getElementById('response').innerText = 'Vous avez déjà répondu à ce quiz !';
        }
    }

    window.sendQuestion = sendQuestion;
    window.sendQuizResponse = sendQuizResponse;
    window.seekToLive = seekToLive;

    document.addEventListener('keydown', function(event) {
        switch (event.key) {
            case 'Red':
                sendQuestion();
                break;
            case 'Green':
                if (!hasAnswered) {
                    const focusedOption = document.activeElement;
                    if (focusedOption && focusedOption.classList.contains('quiz-option')) {
                        const index = Array.from(focusedOption.parentElement.children).indexOf(focusedOption);
                        sendQuizResponse(currentQuizId, index);
                    }
                }
                break;
            case 'Blue':
                seekToLive();
                break;
        }
    });

    checkCurrentSession();
    setInterval(checkCurrentSession, 5000);
});