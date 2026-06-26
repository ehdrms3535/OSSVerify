class OSSVerify {
  constructor(baseUrl = 'http://localhost:8000/api/v1') {
    this.baseUrl = baseUrl;
  }

  async analyzeDeveloper(githubUsername, githubToken = null) {
    const res = await fetch(`${this.baseUrl}/analyze`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ github_username: githubUsername, github_token: githubToken }),
    });
    const body = await res.json();
    return body.data;
  }

  async getProfessionalProfile(githubUsername) {
    const res = await fetch(`${this.baseUrl}/profile/${githubUsername}`);
    const body = await res.json();
    return body.data;
  }

  async issueCredential(githubUsername) {
    const res = await fetch(`${this.baseUrl}/credential/issue`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ github_username: githubUsername }),
    });
    const body = await res.json();
    return body.data;
  }

  async verifyCredential(credentialId) {
    const res = await fetch(`${this.baseUrl}/credential/verify/${credentialId}`);
    const body = await res.json();
    return body.data;
  }
}

module.exports = { OSSVerify };
