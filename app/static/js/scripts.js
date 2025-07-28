let videoSystem = null;
let sessionId = null;
let currentQuizId = null;
let hasAnswered = false; // Suivi de la réponse au quiz
const backendUrl = 'http://localhost:5001';

function initVideoPlayer() {
    const videoPlayer = document.getElementById('video-player');
    if (Hls.isSupported()) {
        console.log('Utilisation de hls.js version:', Hls.version);
        const hls = new Hls({
            debug: true,
            enableWorker: true,
            lowLatencyMode: true,
            maxBufferSize: 600000,
            maxBufferLength: 30,
            liveSyncDurationCount: 3,
            liveMaxLatencyDurationCount: 6,
            xhrSetup: function(xhr, url) {
                xhr.withCredentials = false;
            }
        });
        return { player: videoPlayer, hls: hls };
    } else if (videoPlayer.canPlayType('application/vnd.apple.mpegurl')) {
        console.log('Support HLS natif détecté');
        return videoPlayer;
    } else {
        console.error('Aucun support HLS détecté');
        document.getElementById('response').innerText = 'Votre navigateur ne supporte pas la lecture HLS';
        return null;
    }
}

function loadHlsVideo(hlsUrl, videoSystem) {
    console.log('Chargement du flux HLS:', hlsUrl);
    if (videoSystem instanceof HTMLVideoElement) {
        videoSystem.src = hlsUrl;
        videoSystem.load();
        videoSystem.play().catch(e => {
            console.error('Erreur de lecture native:', e);
            document.getElementById('response').innerText = 'Erreur de lecture du flux HLS: ' + e.message;
        });
    } else if (videoSystem && videoSystem.hls) {
        videoSystem.hls.loadSource(hlsUrl);
        videoSystem.hls.attachMedia(videoSystem.player);
        videoSystem.hls.on(Hls.Events.MANIFEST_PARSED, () => {
            console.log('Manifeste HLS chargé');
            videoSystem.player.play().catch(e => {
                console.error('Erreur de lecture hls.js:', e);
                document.getElementById('response').innerText = 'Erreur de lecture du flux HLS: ' + e.message;
            });
        });
        videoSystem.hls.on(Hls.Events.ERROR, (event, data) => {
            console.error('Erreur hls.js:', data);
            document.getElementById('response').innerText = `Erreur HLS: ${data.type} - ${data.details}`;
            if (data.fatal) {
                switch (data.type) {
                    case Hls.ErrorTypes.NETWORK_ERROR:
                        console.error('Erreur réseau fatale, tentative de récupération...');
                        videoSystem.hls.startLoad();
                        break;
                    case Hls.ErrorTypes.MEDIA_ERROR:
                        console.error('Erreur média fatale, tentative de récupération...');
                        videoSystem.hls.recoverMediaError();
                        break;
                    default:
                        console.error('Erreur irrécupérable, destruction de hls.js');
                        videoSystem.hls.destroy();
                        break;
                }
            }
        });
    }
}

function seekToLive() {
    if (videoSystem && videoSystem.hls) {
        videoSystem.hls.startLoad();
        videoSystem.player.play().catch(e => {
            console.error('Erreur lors du retour en direct:', e);
            document.getElementById('response').innerText = 'Erreur lors du retour en direct: ' + e.message;
        });
    }
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
        hasAnswered = true; // Bloquer d'autres réponses
        document.getElementById('response').innerText = 'Réponse envoyée !';
    }
}

function fetchQuizzes(id) {
    fetch(`${backendUrl}/api/sessions/${id}/quizzes`)
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
                document.getElementById('quiz-question').innerText = quiz.question;
                const optionsList = document.getElementById('quiz-options');
                optionsList.innerHTML = '';
                hasAnswered = false; // Réinitialiser pour le nouveau quiz
                quiz.options.forEach((option, index) => {
                    const li = document.createElement('li');
                    li.innerText = option;
                    li.tabIndex = 0;
                    li.className = 'quiz-option';
                    li.dataset.index = index; // Stocker l'index pour vérification
                    li.onclick = () => sendQuizResponse(quiz.id, index);
                    li.onkeypress = (e) => {
                        if (e.key === 'Enter' && !hasAnswered) sendQuizResponse(quiz.id, index);
                    };
                    optionsList.appendChild(li);
                });
                currentQuizId = quiz.id;
            } else {
                document.getElementById('response').innerText = 'Aucun quiz disponible';
            }
        })
        .catch(error => {
            console.error('Erreur quizzes:', error);
            document.getElementById('response').innerText = 'Erreur lors du chargement des quizzes: ' + error.message;
        });
}

document.addEventListener('DOMContentLoaded', function() {
    videoSystem = initVideoPlayer();
    const socket = io(backendUrl, {
        path: '/socket.io',
        transports: ['websocket'],
        reconnectionAttempts: 5,
        reconnectionDelay: 1000
    });

    socket.on('connect', () => {
        console.log('WebSocket connected');
        document.getElementById('response').innerText = 'Connecté au serveur';
        checkCurrentSession();
    });

    socket.on('connect_error', (error) => {
        console.error('Erreur de connexion WebSocket:', error);
        document.getElementById('response').innerText = 'Erreur de connexion WebSocket: ' + error.message;
    });

    socket.on('disconnect', () => {
        console.log('WebSocket disconnected');
        document.getElementById('response').innerText = 'WebSocket déconnecté';
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
        document.getElementById('quiz-question').innerText = data.question;
        const optionsList = document.getElementById('quiz-options');
        optionsList.innerHTML = '';
        hasAnswered = false; // Réinitialiser pour le nouveau quiz
        data.options.forEach((option, index) => {
            const li = document.createElement('li');
            li.innerText = option;
            li.tabIndex = 0;
            li.className = 'quiz-option';
            li.dataset.index = index;
            li.onclick = () => sendQuizResponse(data.id, index);
            li.onkeypress = (e) => {
                if (e.key === 'Enter' && !hasAnswered) sendQuizResponse(data.id, index);
            };
            optionsList.appendChild(li);
        });
        currentQuizId = data.id;
        // Stocker la bonne réponse si fournie
        if (data.correct_option !== undefined) {
            optionsList.dataset.correctOption = data.correct_option;
        }
    });

    socket.on('quiz_result', (data) => {
        const optionsList = document.getElementById('quiz-options');
        const options = optionsList.querySelectorAll('.quiz-option');
        options.forEach(option => {
            const index = parseInt(option.dataset.index);
            if (index === data.correct_option) {
                option.classList.add('quiz-correct');
                option.innerText += ' ✓'; // Indicateur de bonne réponse
            } else if (index === data.selected_option) {
                option.classList.add('quiz-incorrect');
                option.innerText += ' ✗'; // Indicateur de mauvaise réponse
            }
            option.classList.add('quiz-disabled');
            option.onclick = null; // Désactiver les clics
            option.onkeypress = null; // Désactiver les touches
            option.tabIndex = -1; // Retirer du focus
        });
        document.getElementById('response').innerText = data.selected_option === data.correct_option ? 'Bonne réponse !' : 'Mauvaise réponse, la bonne réponse est en vert.';
    });

    function checkCurrentSession() {
        fetch(`${backendUrl}/api/sessions/current`)
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
                            loadHlsVideo(data.hls_url, videoSystem);
                        }
                        fetchQuizzes(data.id);
                    }
                } else {
                    sessionId = null;
                    document.getElementById('response').innerText = 'Aucune session en direct';
                    if (videoSystem && videoSystem.hls) {
                        videoSystem.hls.destroy();
                    }
                }
            })
            .catch(error => {
                console.error('Erreur API:', error);
                document.getElementById('response').innerText = 'Erreur de connexion au serveur: ' + error.message;
            });
    }

    checkCurrentSession();
    setInterval(checkCurrentSession, 10000);

    window.sendQuestion = sendQuestion;
    window.sendQuizResponse = sendQuizResponse;
    window.seekToLive = seekToLive;

    // Gestion des boutons colorés HbbTV
    document.addEventListener('keydown', function(event) {
        switch (event.key) {
            case 'Red':
                sendQuestion();
                break;
            case 'Green':
                if (!hasAnswered) {
                    const focusedOption = document.activeElement;
                    if (focusedOption && focusedOption.classList.contains('quiz-option')) {
                        const index = parseInt(focusedOption.dataset.index);
                        sendQuizResponse(currentQuizId, index);
                    }
                }
                break;
            case 'Blue':
                seekToLive();
                break;
        }
    });
});