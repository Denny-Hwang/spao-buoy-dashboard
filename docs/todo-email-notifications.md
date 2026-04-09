# TODO: Device Update Email Notification System

> **Status**: Planning  
> **Priority**: Enhancement  
> **Created**: 2026-04-09  
> **Branch**: `claude/device-update-email-notifications-eVLYQ`

---

## 1. Overview

RSS 서비스처럼, 디바이스 데이터 업데이트를 이메일 보고서로 구독/수신할 수 있는 시스템.
신규 사용자도 이메일만 등록하면 보고서를 받아볼 수 있어야 함.

### 핵심 요구사항

- [ ] 이메일 구독 등록/해제 기능
- [ ] 디바이스별 선택적 구독
- [ ] 주기적 보고서 자동 발송 (일간/주간)
- [ ] 새 데이터 수신 시 즉시 알림 (선택)
- [ ] HTML 보고서 형식 (센서 요약, GPS 위치, 상태 등)

---

## 2. Architecture Decision

### Why Google Apps Script?

현재 인프라에서 **추가 서버 없이** 구현 가능한 유일한 방법.

| 대안 | 장점 | 단점 | 판정 |
|------|------|------|------|
| **Apps Script 확장** | 서버 불필요, MailApp 내장, 이미 Sheets 접근 가능 | 일 100건 이메일 제한 (무료), 복잡한 템플릿 어려움 | **채택** |
| SendGrid/Mailgun + Cloud Function | 대량 발송 가능, 풍부한 템플릿 | 별도 서비스 비용, 인프라 추가 | 규모 커지면 전환 |
| Streamlit 내 smtplib | Python 코드로 관리 | Streamlit에는 스케줄러 없음, 항상 실행 필요 | 부적합 |
| n8n / Zapier | 노코드 연동 | 외부 의존성, 비용 | 부적합 |

### Email Quota (Google Apps Script)

- **무료 계정**: 100건/일
- **Google Workspace**: 1,500건/일
- 현재 규모에서는 무료 계정으로 충분

---

## 3. Data Model

### 3.1 `_subscribers` Sheet Tab (신규 생성)

Google Sheets에 새 탭 추가하여 구독자 정보 저장.

| Column | Type | Description | Example |
|--------|------|-------------|---------|
| Email | string | 구독자 이메일 | `user@example.com` |
| Devices | string | 구독 디바이스 IMEI (콤마 구분, `*` = 전체) | `300434005060840,300434007080123` 또는 `*` |
| Frequency | string | 발송 주기 | `daily` / `weekly` / `realtime` |
| Status | string | 구독 상태 | `active` / `paused` / `unsubscribed` |
| Created At | ISO datetime | 등록 시각 | `2026-04-09T10:00:00Z` |
| Last Sent | ISO datetime | 마지막 발송 시각 | `2026-04-09T06:00:00Z` |
| Token | string | 구독 해제용 고유 토큰 | `a1b2c3d4e5f6` |

### 3.2 `_email_log` Sheet Tab (선택, 디버깅용)

| Column | Type | Description |
|--------|------|-------------|
| Sent At | ISO datetime | 발송 시각 |
| Email | string | 수신자 |
| Subject | string | 제목 |
| Devices | string | 포함된 디바이스 |
| Status | string | `sent` / `failed` |
| Error | string | 실패 시 에러 메시지 |

---

## 4. Implementation Plan

### Phase 1: Apps Script - 이메일 발송 엔진

**파일**: `apps_script/Code.gs` (기존 파일에 함수 추가)

#### Task 1.1: 구독자 관리 함수

```javascript
// 추가할 함수 목록:
function getSubscribers(frequency)     // _subscribers 탭에서 active 구독자 조회
function addSubscriber(email, devices, frequency)  // 새 구독자 추가
function removeSubscriber(token)       // 토큰 기반 구독 해제
function generateToken()               // 랜덤 해제 토큰 생성
```

#### Task 1.2: 보고서 생성 함수

```javascript
function buildReportHTML(imei, rows)   // 디바이스별 HTML 보고서 생성
function getRecentData(imei, since)    // 특정 시점 이후 데이터 조회
```

**보고서에 포함할 항목:**
- 디바이스 닉네임 + IMEI
- 기간 내 수신된 패킷 수
- 최신 데이터: Battery, GPS, SST, Pressure, Humidity, TENG
- Battery 트렌드 (상승/하락/안정)
- CRC 유효성 비율
- GPS 최종 위치 (Google Static Maps 이미지 링크)
- 대시보드 바로가기 링크

#### Task 1.3: 발송 함수

```javascript
function sendDailyReport()    // 일간 보고서 발송 (매일 오전 9시)
function sendWeeklyReport()   // 주간 보고서 발송 (매주 월요일 오전 9시)
function sendRealtimeAlert()  // 새 데이터 수신 시 즉시 알림 (doPost 내에서 호출)
```

#### Task 1.4: 시간 기반 트리거 설정

```javascript
function setupTriggers() {
  // 매일 오전 9시 (KST) daily 보고서
  ScriptApp.newTrigger('sendDailyReport')
    .timeBased().everyDays(1).atHour(0)  // UTC 0시 = KST 9시
    .create();
  
  // 매주 월요일 오전 9시 (KST) weekly 보고서
  ScriptApp.newTrigger('sendWeeklyReport')
    .timeBased().onWeekDay(ScriptApp.WeekDay.SUNDAY)  // UTC 일요일 = KST 월요일
    .atHour(0).create();
}
```

#### Task 1.5: 실시간 알림 (doPost 확장)

기존 `doPost()` 함수의 데이터 저장 후에 realtime 구독자에게 즉시 알림 발송.

```javascript
// doPost() 끝부분에 추가:
try {
  notifyRealtimeSubscribers(imei, result);
} catch (notifyErr) {
  // 알림 실패가 데이터 저장을 방해하지 않도록
}
```

---

### Phase 2: Streamlit - 구독 관리 UI

**파일**: `pages/6_📧_Subscribe.py` (신규 페이지)

#### Task 2.1: 구독 등록 폼

```python
# UI 구성 요소:
- st.text_input("이메일 주소")
- st.multiselect("구독할 디바이스", options=device_list)  # 또는 "전체 디바이스"
- st.selectbox("발송 주기", ["daily", "weekly", "realtime"])
- st.button("구독하기")
```

#### Task 2.2: 구독 해제 폼

```python
# URL 파라미터로 토큰 전달: ?unsubscribe=TOKEN
- st.text_input("이메일 주소")
- st.button("구독 해제")
```

#### Task 2.3: sheets_client.py 확장

```python
# utils/sheets_client.py에 추가할 함수:
def get_subscribers() -> pd.DataFrame
def add_subscriber(email: str, devices: list, frequency: str) -> bool
def update_subscriber_status(email: str, status: str) -> bool
def remove_subscriber(token: str) -> bool
```

---

### Phase 3: HTML 이메일 템플릿

**파일**: `apps_script/email_template.html` (참조용, 실제로는 Apps Script 내 문자열)

#### 보고서 레이아웃 (설계)

```
┌─────────────────────────────────────────────┐
│  🔵 SPAO Buoy Daily Report                  │
│  2026-04-09 | 3 devices updated             │
├─────────────────────────────────────────────┤
│                                             │
│  📡 Device: Buoy-Alpha (300434005060840)    │
│  ┌─────────────────────────────────────┐    │
│  │ New Packets: 5                      │    │
│  │ Battery: 3.82V (▼ -0.03V)         │    │
│  │ Last GPS: 37.5°N, 126.9°E          │    │
│  │ SST: 12.3°C                         │    │
│  │ Pressure: 14.7 psi                  │    │
│  │ CRC Valid: 100%                     │    │
│  └─────────────────────────────────────┘    │
│  [View on Dashboard →]                      │
│                                             │
│  📡 Device: Buoy-Beta (300434007080123)     │
│  ┌─────────────────────────────────────┐    │
│  │ ...                                 │    │
│  └─────────────────────────────────────┘    │
│                                             │
├─────────────────────────────────────────────┤
│  Unsubscribe: [click here]                  │
│  SPAO Buoy Dashboard — PNNL                 │
└─────────────────────────────────────────────┘
```

---

## 5. File Changes Summary

| File | Action | Description |
|------|--------|-------------|
| `apps_script/Code.gs` | **수정** | 구독자 관리, 보고서 생성, 발송, 트리거 함수 추가 |
| `pages/6_📧_Subscribe.py` | **신규** | 이메일 구독 관리 Streamlit 페이지 |
| `utils/sheets_client.py` | **수정** | `_subscribers` 탭 CRUD 함수 추가 |
| `requirements.txt` | 변경 없음 | 추가 패키지 불필요 (gspread로 충분) |
| `.streamlit/secrets.toml` | 변경 없음 | 기존 GCP 서비스 계정 재사용 |

---

## 6. Security Considerations

- [ ] 이메일 주소 유효성 검증 (regex)
- [ ] 구독 해제 토큰은 UUID v4 사용 (추측 불가)
- [ ] 이메일 보고서에 민감 정보 포함 여부 검토
- [ ] Rate limiting: 동일 이메일 중복 등록 방지
- [ ] 구독 해제 링크 모든 이메일에 필수 포함 (CAN-SPAM 준수)
- [ ] `_subscribers` 탭 접근 권한 관리 (서비스 계정만 쓰기 가능)

---

## 7. Testing Checklist

- [ ] 구독 등록 → `_subscribers` 탭에 정상 추가 확인
- [ ] 중복 이메일 등록 시 에러 처리 확인
- [ ] Daily 트리거 → 이메일 정상 수신 확인
- [ ] Weekly 트리거 → 이메일 정상 수신 확인
- [ ] Realtime 알림 → 새 데이터 수신 후 즉시 이메일 도착 확인
- [ ] 구독 해제 → 토큰 기반 해제 동작 확인
- [ ] 보고서 HTML 렌더링 → 주요 이메일 클라이언트 호환성 (Gmail, Outlook)
- [ ] 디바이스 없는 기간의 보고서 → 빈 보고서 처리 확인
- [ ] MailApp 일일 할당량 초과 시 에러 핸들링 확인

---

## 8. Future Enhancements (Optional)

- [ ] 임계값 기반 알림 (배터리 < 3.0V, CRC 실패율 > 20% 등)
- [ ] 보고서 포맷 선택 (HTML / Plain Text / PDF 첨부)
- [ ] Google Static Maps API로 위치 이미지 포함
- [ ] 구독자별 타임존 설정
- [ ] SendGrid/Mailgun 전환 (대량 발송 필요 시)
- [ ] Slack/Teams webhook 알림 연동
- [ ] 보고서 열람 추적 (이메일 open tracking pixel)

---

## 9. Implementation Order (Recommended)

```
Phase 1.1 → 1.2 → 1.3 → 1.4 (Apps Script 핵심 기능)
     ↓
Phase 2.1 → 2.2 → 2.3 (Streamlit UI)
     ↓
Phase 1.5 (실시간 알림 — 안정화 후 추가)
     ↓
Phase 3 (HTML 템플릿 개선)
```

예상 작업량: Phase 1 (핵심) ~2-3시간, Phase 2 (UI) ~1-2시간, Phase 3 (템플릿) ~1시간
