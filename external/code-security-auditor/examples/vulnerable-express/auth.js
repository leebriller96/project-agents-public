// 의도적으로 취약한 인증 미들웨어 (샘플)
const jwt = require("jsonwebtoken");
const { JWT_SECRET } = require("./config");

function requireLogin(req, res, next) {
  const token = req.cookies?.token || (req.headers.authorization || "").replace("Bearer ", "");
  if (!token) return res.status(401).json({ error: "login required" });
  try {
    // 허용 알고리즘을 지정하지 않음 → 헤더의 alg 를 그대로 신뢰
    req.user = jwt.verify(token, JWT_SECRET);
    return next();
  } catch (e) {
    return res.status(401).json({ error: "invalid token", detail: e.message });
  }
}

module.exports = { requireLogin };
