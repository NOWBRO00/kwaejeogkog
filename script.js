import { initializeApp } from "https://www.gstatic.com/firebasejs/12.6.0/firebase-app.js";
import { getDatabase, ref, onValue } from "https://www.gstatic.com/firebasejs/12.6.0/firebase-database.js";

// 🔥 Firebase 설정 (config.py의 FIREBASE_URL과 일치해야 함)
const firebaseConfig = {
    apiKey: "AIzaSyDWH90Y8X75NKUhCrnrCZmqqopBrk5-d-s",
    authDomain: "cozy-seat.firebaseapp.com",
    databaseURL: "https://cozy-seat-default-rtdb.firebaseio.com",
    projectId: "cozy-seat",
    storageBucket: "cozy-seat.firebasestorage.app",
    messagingSenderId: "729612462742",
    appId: "1:729612462742:web:daea5b07fd6dadb4b330b7",
    measurementId: "G-JVR96DE719"
};

// Firebase 초기화
const app = initializeApp(firebaseConfig);
const database = getDatabase(app);
const seatRef = ref(database, "seats");
const systemStatusRef = ref(database, "system_status");

const seatGrid = document.getElementById("seatGrid");
const bestSeatEl = document.getElementById("bestSeat");
const seatPositionsRef = ref(database, "seat_positions");
const globalSoundRef = ref(database, "global_sound");

// 좌석 위치 정보 저장
let seatPositions = {};
// 통합 소음 데이터 저장
let globalSoundData = { decibel: 45.0, status: "조용함" };

// 좌석 위치 정보 수신
onValue(seatPositionsRef, (snapshot) => {
    const positions = snapshot.val();
    if (positions) {
        seatPositions = positions;
        console.log("좌석 위치 정보 업데이트:", positions);
    }
});

// 통합 소음 데이터 수신
onValue(globalSoundRef, (snapshot) => {
    const soundData = snapshot.val();
    if (soundData) {
        globalSoundData = soundData;
        // 통합 소음 정보를 상단에 표시
        const decibel = soundData.decibel || 0;
        const status = soundData.status || "조용함";
        const soundEl = document.getElementById("global-sound");
        if (soundEl) {
            soundEl.textContent = `${decibel.toFixed(1)}dB (${status})`;
            soundEl.style.color = status === "소음" ? "#f44336" : "#4caf50";
        }
        console.log("통합 소음 데이터 업데이트:", soundData);
    }
});

// 시스템 연결 상태 확인
let isSystemOnline = false;

// 시스템 상태 수신
onValue(systemStatusRef, (snapshot) => {
    const statusData = snapshot.val() || {};
    isSystemOnline = statusData.connection === 'online';
    
    document.getElementById("system-status").textContent = isSystemOnline ? "온라인" : "오프라인";
    document.getElementById("system-status").style.color = isSystemOnline ? "#4caf50" : "#f44336";
    document.getElementById("fps").textContent = statusData.fps ? statusData.fps.toFixed(1) : "0.0";
    document.getElementById("inference-ms").textContent = statusData.inference_ms ? `${statusData.inference_ms.toFixed(1)} ms` : "0.0 ms";
    
    if (statusData.last_update) {
        document.getElementById("last-update").textContent = statusData.last_update;
    } else if (statusData.last_boot) {
        const lastUpdate = new Date(statusData.last_boot);
        document.getElementById("last-update").textContent = lastUpdate.toLocaleTimeString('ko-KR');
    }
});

// Firebase 실시간 데이터 리스너
onValue(seatRef, (snapshot) => {
    const data = snapshot.val();
    
    // 시스템이 오프라인이고 데이터가 있으면 경고 표시
    if (!isSystemOnline && data) {
        seatGrid.innerHTML = '<div class="loading" style="color: #f44336; padding: 20px; background: #ffebee; border-radius: 10px; margin-bottom: 20px;">⚠️ Python 프로그램이 실행되지 않았습니다. 아래는 이전 데이터입니다.<br>Python 프로그램을 실행하면 실시간 데이터가 표시됩니다.</div>';
    }
    
    if (!data) {
        seatGrid.innerHTML = '<div class="loading">데이터가 없습니다. Python 프로그램이 실행 중인지 확인하세요.</div>';
        updateStats(0, 0, 0, 0);
        bestSeatEl.textContent = "없음";
        return;
    }

    seatGrid.innerHTML = "";
    let bestSeat = null;
    let bestDI = 999;
    let total = 0, occupied = 0, vacant = 0, ghost = 0;

    // 좌석 데이터를 seat1, seat2, ... 순서로 정렬
    const sortedSeats = Object.keys(data).sort((a, b) => {
        const numA = parseInt(a.replace('seat', ''));
        const numB = parseInt(b.replace('seat', ''));
        return numA - numB;
    });

    sortedSeats.forEach((seatId) => {
        const seat = data[seatId];
        
        // 좌석 위치 정보 확인 - 위치 정보가 없으면 표시하지 않음 (실제 설정되지 않은 좌석)
        const positionInfo = seatPositions[seatId] || null;
        if (!positionInfo && Object.keys(seatPositions).length > 0) {
            // 좌석 위치 정보가 있고, 이 좌석이 없으면 스킵 (실제 설정되지 않은 좌석)
            return;
        }
        
        total++;
        
        // 좌석 번호 추출
        const seatNumber = parseInt(seatId.replace('seat', ''));
        
        const environment = seat.environment || (positionInfo ? positionInfo.environment : null);
        const seasonKr = seat.season_kr || (positionInfo ? positionInfo.season_kr : null);
        
        // 상태 확인 (기존 호환성 유지)
        const status = typeof seat === 'string' ? seat : (seat.status || 'Vacant');
        
        // 통계 업데이트
        if (status === 'Occupied') occupied++;
        else if (status === 'Ghost') ghost++;
        else vacant++;
        
        // 온도/습도 데이터 가져오기
        const temp = seat.temp !== undefined ? (typeof seat.temp === 'number' ? seat.temp : parseFloat(seat.temp)) : null;
        const hum = seat.hum !== undefined ? (typeof seat.hum === 'number' ? seat.hum : parseFloat(seat.hum)) : null;
        const DI = seat.DI !== undefined ? (typeof seat.DI === 'number' ? seat.DI : parseFloat(seat.DI)) : null;
        
        // 소음은 통합 데이터 사용
        const decibel = globalSoundData.decibel !== undefined ? (typeof globalSoundData.decibel === 'number' ? globalSoundData.decibel : parseFloat(globalSoundData.decibel)) : null;
        const soundStatus = globalSoundData.status || (decibel !== null && decibel >= 60 ? "소음" : "조용함");
        const isNoisy = soundStatus === "소음" || (decibel !== null && decibel >= 60);
        
        // 좌석 점유 상태 (카메라에서 감지한 상태)
        const occupancyStatus = seat.occupancy_status || (status === 'Occupied' ? 'occupied' : status === 'Ghost' ? 'ghost' : 'vacant');
        const occupancyStatusKr = seat.occupancy_status_kr || (status === 'Occupied' ? '점유' : status === 'Ghost' ? '유령' : '공석');
        const occupancyIcons = {
            "occupied": "🪑",
            "wait": "⏳",
            "ghost": "👻",
            "vacant": "✅"
        };
        const occupancyIcon = occupancyIcons[occupancyStatus] || "❓";
        
        // 쾌적 상태 (Python에서 계산된 상태 사용)
        const comfortStatus = seat.comfort_status || seat.status || "쾌적";
        
        // 색상 결정
        let statusClass = "status-good";
        if (comfortStatus.includes("매우 추움")) {
            statusClass = "status-very-cold";
        } else if (comfortStatus.includes("약간 추움")) {
            statusClass = "status-cold";
        } else if (comfortStatus.includes("매우 더움")) {
            statusClass = "status-very-hot";
        } else if (comfortStatus.includes("다소 덥고 습함")) {
            statusClass = "status-mid";
        } else if (comfortStatus.includes("건조함")) {
            statusClass = "status-dry";
        } else if (comfortStatus.includes("쾌적")) {
            statusClass = "status-good";
        } else {
            // 백업 로직
            if (DI !== null) {
                if (DI >= 75) {
                    statusClass = "status-very-hot";
                } else if (DI >= 68) {
                    statusClass = "status-mid";
                } else {
                    statusClass = "status-good";
                }
            }
        }
        
        // 좌석 카드 HTML 생성
        const seatCard = document.createElement("div");
        seatCard.className = `seat ${statusClass}`;
        
        // 소음 정보 HTML
        const soundHTML = decibel !== null ? `
            <div class="sound-info ${isNoisy ? 'noisy' : 'quiet'}">
                <span class="sound-icon">${isNoisy ? '🔊' : '🔇'}</span>
                <span class="sound-value">${decibel.toFixed(1)}dB</span>
                <span class="sound-status ${isNoisy ? 'noisy' : 'quiet'}">${soundStatus}</span>
            </div>
        ` : '';
        
        // 좌석 점유 상태 HTML
        const occupancyHTML = `
            <div class="occupancy-info ${occupancyStatus}">
                <span class="occupancy-icon">${occupancyIcon}</span>
                <span class="occupancy-label">${occupancyStatusKr}</span>
            </div>
        `;
        
        // 환경 정보 표시
        const environmentHTML = environment ? `
            <div style="margin-top: 10px; padding: 8px; background: ${seasonKr === '여름' ? '#fff3e0' : '#e3f2fd'}; border-radius: 8px; font-size: 0.9em; text-align: center; font-weight: bold; color: ${seasonKr === '여름' ? '#e65100' : '#1565c0'};">
                ${seasonKr ? `🌡️ ${environment}` : environment}
            </div>
        ` : '';
        
        // 냉난방기 상태 가져오기 (Firebase에서 boolean 값이 문자열로 올 수 있음)
        const heaterOn = seat.heater_on === true || seat.heater_on === 'true' || seat.heater_on === 1 || seat.heater_on === '1';
        const coolerOn = seat.cooler_on === true || seat.cooler_on === 'true' || seat.cooler_on === 1 || seat.cooler_on === '1';
        const targetTemp = typeof seat.target_temp === 'number' ? seat.target_temp : (seat.target_temp ? parseFloat(seat.target_temp) : 22.0);
        const controlAction = seat.control_action || "유지";
        const hasActiveHVAC = heaterOn || coolerOn;
        
        // 냉난방기 상태 HTML (항상 표시)
        const hvacHTML = `
            <div class="hvac-control ${hasActiveHVAC ? 'has-active' : ''}" style="margin-top: 15px;">
                <div class="hvac-item heater ${heaterOn ? 'active' : ''}" style="display: flex; align-items: center; gap: 10px; padding: 8px; margin-bottom: 8px; border-radius: 8px; background: ${heaterOn ? 'linear-gradient(135deg, #ff6b6b 0%, #ee5a6f 100%)' : '#e0e0e0'}; color: ${heaterOn ? 'white' : '#333'}; transition: all 0.3s;">
                    <span style="font-size: 1.5em;">🔥</span>
                    <span style="flex: 1; font-weight: bold;">난방</span>
                    <span style="font-weight: bold; padding: 4px 12px; border-radius: 15px; background: ${heaterOn ? 'rgba(255, 255, 255, 0.4)' : 'rgba(255, 255, 255, 0.3)'};">${heaterOn ? 'ON' : 'OFF'}</span>
                </div>
                <div class="hvac-item cooler ${coolerOn ? 'active' : ''}" style="display: flex; align-items: center; gap: 10px; padding: 8px; margin-bottom: 8px; border-radius: 8px; background: ${coolerOn ? 'linear-gradient(135deg, #4facfe 0%, #00f2fe 100%)' : '#e0e0e0'}; color: ${coolerOn ? 'white' : '#333'}; transition: all 0.3s;">
                    <span style="font-size: 1.5em;">❄️</span>
                    <span style="flex: 1; font-weight: bold;">냉방</span>
                    <span style="font-weight: bold; padding: 4px 12px; border-radius: 15px; background: ${coolerOn ? 'rgba(255, 255, 255, 0.4)' : 'rgba(255, 255, 255, 0.3)'};">${coolerOn ? 'ON' : 'OFF'}</span>
                </div>
                <div style="margin-top: 8px; padding-top: 8px; border-top: 1px solid ${hasActiveHVAC ? 'rgba(255, 255, 255, 0.3)' : '#ddd'}; text-align: center; font-size: 0.85em; color: #000; font-weight: bold;">
                    목표: ${typeof targetTemp === 'number' ? targetTemp.toFixed(1) : targetTemp}°C (${controlAction})
                </div>
            </div>
        `;
        
        seatCard.innerHTML = `
            <h3>${seatId}</h3>
            ${occupancyHTML}
            ${environmentHTML}
            ${temp !== null ? `<p>온도: <strong>${temp}°C</strong></p>` : ''}
            ${hum !== null ? `<p>습도: <strong>${hum}%</strong></p>` : ''}
            ${soundHTML}
            ${DI !== null ? `<p class="di-value">쾌적 지수: ${DI.toFixed(1)}</p>` : ''}
            <strong>${comfortStatus}</strong>
            ${hvacHTML}
        `;
        
        seatGrid.appendChild(seatCard);

        // 가장 쾌적한 좌석 찾기
        if (DI !== null) {
            let adjustedDI = DI;
            if (isNoisy) adjustedDI += 5;
            if (occupancyStatus === "occupied") adjustedDI += 10;
            if (occupancyStatus === "ghost") adjustedDI += 15;
            if (occupancyStatus === "wait") adjustedDI += 8;
            
            if (adjustedDI < bestDI) {
                bestDI = adjustedDI;
                bestSeat = seatId;
            }
        }
    });

    // 통계 업데이트
    updateStats(total, occupied, vacant, ghost);

    // 가장 쾌적한 좌석 표시
    if (bestSeat) {
        bestSeatEl.textContent = bestSeat;
    } else {
        bestSeatEl.textContent = "없음";
    }
}, (error) => {
    console.error("Firebase 오류:", error);
    seatGrid.innerHTML = '<div class="loading">데이터를 불러오는 중 오류가 발생했습니다. Firebase 설정을 확인하세요.</div>';
    bestSeatEl.textContent = "오류";
});

function updateStats(total, occupied, vacant, ghost) {
    document.getElementById("total-seats").textContent = total;
    document.getElementById("occupied-seats").textContent = occupied;
    document.getElementById("vacant-seats").textContent = vacant;
    document.getElementById("ghost-seats").textContent = ghost;
}

