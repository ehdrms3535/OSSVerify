/**
 * OSSVerify JavaScript SDK
 *
 * Usage:
 *   const client = new OSSVerifyClient('http://localhost:8000');
 *   const result = await client.analyze('torvalds', { githubToken: 'ghp_...' });
 *   const vc = await client.issueCredential('torvalds');
 *   const verified = await client.verifyDocument(vc.document);
 */

(function (root, factory) {
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = factory();          // Node.js / CommonJS
  } else {
    root.OSSVerifyClient = factory();    // 브라우저 전역
  }
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {

  class OSSVerifyError extends Error {
    constructor(message, code, statusCode) {
      super(message);
      this.name = 'OSSVerifyError';
      this.code = code || 'UNKNOWN';
      this.statusCode = statusCode || 0;
    }
  }

  class OSSVerifyClient {
    /**
     * @param {string} baseUrl   - OSSVerify 서버 URL (기본값: http://localhost:8000)
     * @param {object} [options]
     * @param {number} [options.pollInterval=5000]  - 분석 폴링 간격 (ms)
     * @param {number} [options.timeout=300000]     - 분석 최대 대기 시간 (ms)
     */
    constructor(baseUrl = 'http://localhost:8000', options = {}) {
      this.baseUrl = baseUrl.replace(/\/$/, '');
      this.pollInterval = options.pollInterval ?? 5000;
      this.timeout = options.timeout ?? 300_000;
    }

    // ── 분석 ───────────────────────────────────────────────────────────────

    /**
     * GitHub 사용자를 분석한다. 완료될 때까지 자동 폴링.
     * @param {string} username
     * @param {{ githubToken?: string, onProgress?: function }} [options]
     * @returns {Promise<object>} AnalysisResult
     */
    async analyze(username, options = {}) {
      const payload = { github_username: username };
      if (options.githubToken) payload.github_token = options.githubToken;

      const { data } = await this._post('/api/v1/analyze', payload);
      return this._poll(data.job_id, options.onProgress);
    }

    /**
     * 본인 인증 분석. github_token 의 GitHub 사용자 == username 이어야 한다.
     * @param {string} username
     * @param {string} githubToken  - Bearer 토큰
     * @param {{ onProgress?: function }} [options]
     * @returns {Promise<object>} AnalysisResult
     */
    async analyzeSelf(username, githubToken, options = {}) {
      const { data } = await this._post(
        '/api/v1/analyze/self',
        { github_username: username },
        { authToken: githubToken },
      );
      return this._poll(data.job_id, options.onProgress);
    }

    /**
     * 분석 작업 상태를 단 1회 조회한다 (폴링 없이).
     * @param {string} jobId
     * @returns {Promise<{status: string, data: object|null, error: string|null}>}
     */
    async getJobStatus(jobId) {
      const { data } = await this._get(`/api/v1/analyze/status/${jobId}`);
      return data;
    }

    /**
     * 이미 분석된 프로필을 조회한다.
     * @param {string} username
     * @returns {Promise<object>} AnalysisResult
     */
    async getProfile(username) {
      const { data } = await this._get(`/api/v1/profile/${encodeURIComponent(username)}`);
      return data;
    }

    // ── VC 발급·앵커링·검증 ─────────────────────────────────────────────────

    /**
     * 분석 결과를 기반으로 VC를 발급한다 (서명만, 블록체인 기록 없음).
     * @param {string} username
     * @returns {Promise<object>} VerifiableCredential
     */
    async issueCredential(username) {
      const { data } = await this._post('/api/v1/credential/issue', {
        github_username: username,
      });
      return data;
    }

    /**
     * 발급된 VC를 Polygon Amoy 온체인에 앵커링한다. 본인 인증 필요.
     * @param {string} credentialId
     * @param {string} githubToken
     * @returns {Promise<object>} AnchorResult
     */
    async anchorCredential(credentialId, githubToken) {
      const { data } = await this._post(
        '/api/v1/credential/anchor',
        { credential_id: credentialId },
        { authToken: githubToken },
      );
      return data;
    }

    /**
     * credential_id 로 VC를 검증한다.
     * @param {string} credentialId
     * @returns {Promise<object>} VerificationResult
     */
    async verifyCredential(credentialId) {
      const { data } = await this._get(
        `/api/v1/credential/verify/${encodeURIComponent(credentialId)}`,
      );
      return data;
    }

    /**
     * VC 문서를 직접 검증한다. 다른 인스턴스가 발급한 VC도 검증 가능.
     * @param {object} document - VC JSON 문서
     * @returns {Promise<object>} VerificationResult
     */
    async verifyDocument(document) {
      const { data } = await this._post('/api/v1/credential/verify', { document });
      return data;
    }

    // ── 내부 헬퍼 ──────────────────────────────────────────────────────────

    async _poll(jobId, onProgress) {
      const deadline = Date.now() + this.timeout;
      while (true) {
        const job = await this.getJobStatus(jobId);
        if (onProgress) onProgress(job.status);
        if (job.status === 'complete') return job.data;
        if (job.status === 'failed') throw new OSSVerifyError(job.error || 'analysis failed', 'ANALYSIS_FAILED');
        if (Date.now() > deadline) throw new OSSVerifyError(`Analysis timed out (job_id=${jobId})`, 'TIMEOUT');
        await new Promise(r => setTimeout(r, this.pollInterval));
      }
    }

    async _get(path) {
      return this._request('GET', path, null, {});
    }

    async _post(path, body, options = {}) {
      return this._request('POST', path, body, options);
    }

    async _request(method, path, body, options) {
      const headers = { 'Content-Type': 'application/json' };
      if (options.authToken) headers['Authorization'] = `Bearer ${options.authToken}`;

      const init = { method, headers };
      if (body !== null) init.body = JSON.stringify(body);

      const resp = await fetch(`${this.baseUrl}${path}`, init);
      let json;
      try { json = await resp.json(); } catch { throw new OSSVerifyError(resp.statusText, 'PARSE_ERROR', resp.status); }

      if (!json.success) {
        const err = json.error || {};
        throw new OSSVerifyError(err.message || resp.statusText, err.code, resp.status);
      }
      return json;
    }
  }

  OSSVerifyClient.OSSVerifyError = OSSVerifyError;
  return OSSVerifyClient;
});
