// 샘플 엔티티. role 필드가 요청 바디에서 그대로 바인딩된다 (Mass Assignment 검증용).
package com.example.shop;

public class User {
    private String email;
    private String displayName;
    private String role;

    public String getEmail() { return email; }
    public void setEmail(String email) { this.email = email; }
    public String getDisplayName() { return displayName; }
    public void setDisplayName(String displayName) { this.displayName = displayName; }
    public String getRole() { return role; }
    public void setRole(String role) { this.role = role; }
}
