"""
HallucinationReporter for generating comprehensive reports on AI script validation.
"""
import logging
from typing import Dict, Any, List
from datetime import datetime

logger = logging.getLogger(__name__)

class HallucinationReporter:
    """Generate comprehensive reports on AI script hallucination detection results."""
    
    def __init__(self):
        """Initialize the hallucination reporter."""
        pass
    
    def generate_comprehensive_report(self, validation_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate a comprehensive report from validation results.
        
        Args:
            validation_result: Results from KnowledgeGraphValidator
            
        Returns:
            Dict containing formatted report with analysis and recommendations
        """
        report = {
            "timestamp": datetime.now().isoformat(),
            "summary": self._generate_summary(validation_result),
            "confidence_analysis": self._analyze_confidence(validation_result),
            "issue_breakdown": self._categorize_issues(validation_result),
            "validated_components": self._format_validated_components(validation_result),
            "recommendations": self._generate_recommendations(validation_result),
            "risk_assessment": self._assess_risk(validation_result),
            "actionable_items": self._generate_action_items(validation_result)
        }
        
        return report
    
    def _generate_summary(self, validation_result: Dict[str, Any]) -> Dict[str, Any]:
        """Generate executive summary of the validation."""
        hallucinations_detected = validation_result.get("hallucinations_detected", False)
        confidence_score = validation_result.get("confidence_score", 0.0)
        total_issues = len(validation_result.get("issues", []))
        total_validated = len(validation_result.get("validated_components", []))
        
        if hallucinations_detected:
            if confidence_score < 0.3:
                verdict = "CRITICAL - High likelihood of hallucinations"
                color = "red"
            elif confidence_score < 0.5:
                verdict = "WARNING - Moderate hallucination risk"
                color = "orange"
            else:
                verdict = "CAUTION - Minor concerns detected"
                color = "yellow"
        else:
            if confidence_score > 0.9:
                verdict = "EXCELLENT - High confidence in script validity"
                color = "green"
            elif confidence_score > 0.7:
                verdict = "GOOD - Script appears valid with minor concerns"
                color = "lightgreen"
            else:
                verdict = "ACCEPTABLE - Script validation passed with reservations"
                color = "yellow"
        
        return {
            "verdict": verdict,
            "confidence_score": confidence_score,
            "color_indicator": color,
            "hallucinations_detected": hallucinations_detected,
            "total_issues": total_issues,
            "total_validated_components": total_validated,
            "validation_ratio": round(total_validated / max(total_validated + total_issues, 1), 2)
        }
    
    def _analyze_confidence(self, validation_result: Dict[str, Any]) -> Dict[str, Any]:
        """Provide detailed confidence analysis."""
        confidence_score = validation_result.get("confidence_score", 0.0)
        
        if confidence_score >= 0.9:
            level = "Very High"
            description = "Script components are well-validated against known patterns"
        elif confidence_score >= 0.7:
            level = "High"
            description = "Most script components validated successfully"
        elif confidence_score >= 0.5:
            level = "Medium"
            description = "Mixed validation results with some concerns"
        elif confidence_score >= 0.3:
            level = "Low"
            description = "Significant validation issues detected"
        else:
            level = "Very Low"
            description = "Major validation failures, high hallucination risk"
        
        factors = []
        
        # Analyze what contributed to the confidence score
        issues = validation_result.get("issues", [])
        validated = validation_result.get("validated_components", [])
        
        if len(validated) > 0:
            factors.append(f"✓ {len(validated)} components successfully validated")
        
        issue_types = {}
        for issue in issues:
            issue_type = issue.get("type", "unknown")
            issue_types[issue_type] = issue_types.get(issue_type, 0) + 1
        
        for issue_type, count in issue_types.items():
            factors.append(f"⚠ {count} {issue_type.replace('_', ' ')} issue(s)")
        
        return {
            "level": level,
            "score": confidence_score,
            "description": description,
            "contributing_factors": factors
        }
    
    def _categorize_issues(self, validation_result: Dict[str, Any]) -> Dict[str, Any]:
        """Categorize and analyze issues by type and severity."""
        issues = validation_result.get("issues", [])
        
        categories = {
            "critical": [],
            "warning": [],
            "info": []
        }
        
        severity_mapping = {
            "high": "critical",
            "medium": "warning",
            "low": "info"
        }
        
        type_descriptions = {
            "unknown_import": "Unrecognized or unverified import statements",
            "suspicious_function": "Function patterns that may indicate hallucination",
            "unverified_external_call": "External API or service calls that couldn't be validated",
            "suspicious_file_operation": "Potentially dangerous file system operations"
        }
        
        for issue in issues:
            severity = issue.get("severity", "medium")
            category = severity_mapping.get(severity, "warning")
            
            formatted_issue = {
                "type": issue.get("type", "unknown"),
                "description": type_descriptions.get(issue.get("type", ""), issue.get("message", "")),
                "component": issue.get("component", ""),
                "message": issue.get("message", ""),
                "severity": severity
            }
            
            categories[category].append(formatted_issue)
        
        return {
            "critical": categories["critical"],
            "warning": categories["warning"],
            "info": categories["info"],
            "total_by_severity": {
                "critical": len(categories["critical"]),
                "warning": len(categories["warning"]),
                "info": len(categories["info"])
            }
        }
    
    def _format_validated_components(self, validation_result: Dict[str, Any]) -> Dict[str, Any]:
        """Format validated components for the report."""
        components = validation_result.get("validated_components", [])
        
        by_type = {}
        for component in components:
            comp_type = component.get("type", "unknown")
            if comp_type not in by_type:
                by_type[comp_type] = []
            by_type[comp_type].append(component)
        
        summary = {}
        for comp_type, items in by_type.items():
            summary[comp_type] = {
                "count": len(items),
                "items": items[:5],  # Show first 5 items
                "has_more": len(items) > 5
            }
        
        return {
            "by_type": summary,
            "total_count": len(components),
            "types_validated": list(by_type.keys())
        }
    
    def _generate_recommendations(self, validation_result: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate actionable recommendations based on validation results."""
        recommendations = []
        
        confidence_score = validation_result.get("confidence_score", 0.0)
        issues = validation_result.get("issues", [])
        
        # General recommendations based on confidence score
        if confidence_score < 0.5:
            recommendations.append({
                "priority": "high",
                "category": "overall",
                "title": "Manual Review Required",
                "description": "Low confidence score indicates potential hallucinations. Manual review recommended.",
                "action": "Have a human expert review the script before deployment"
            })
        
        # Issue-specific recommendations
        issue_types = set(issue.get("type", "") for issue in issues)
        
        if "unknown_import" in issue_types:
            recommendations.append({
                "priority": "medium",
                "category": "imports",
                "title": "Verify Import Dependencies",
                "description": "Some imports could not be validated against known libraries",
                "action": "Check if imports are correct and install missing dependencies"
            })
        
        if "suspicious_function" in issue_types:
            recommendations.append({
                "priority": "high",
                "category": "functions",
                "title": "Review Function Implementations",
                "description": "Some functions show patterns suggesting potential hallucination",
                "action": "Manually verify function logic and test implementations"
            })
        
        if "suspicious_file_operation" in issue_types:
            recommendations.append({
                "priority": "critical",
                "category": "security",
                "title": "Security Review Required",
                "description": "Potentially dangerous file operations detected",
                "action": "Security team should review file operations before execution"
            })
        
        if "unverified_external_call" in issue_types:
            recommendations.append({
                "priority": "medium",
                "category": "external_apis",
                "title": "Verify External API Usage",
                "description": "External API calls could not be validated",
                "action": "Check API documentation and test endpoints"
            })
        
        # Positive recommendations
        if confidence_score > 0.8 and len(issues) == 0:
            recommendations.append({
                "priority": "low",
                "category": "validation",
                "title": "Script Validation Successful",
                "description": "Script passed validation with high confidence",
                "action": "Consider adding automated tests to maintain quality"
            })
        
        return recommendations
    
    def _assess_risk(self, validation_result: Dict[str, Any]) -> Dict[str, Any]:
        """Assess overall risk level and provide risk analysis."""
        confidence_score = validation_result.get("confidence_score", 0.0)
        issues = validation_result.get("issues", [])
        
        # Calculate risk factors
        critical_issues = sum(1 for issue in issues if issue.get("severity") == "high")
        medium_issues = sum(1 for issue in issues if issue.get("severity") == "medium")
        
        # Determine risk level
        if confidence_score < 0.3 or critical_issues > 2:
            risk_level = "HIGH"
            risk_color = "red"
            risk_description = "High probability of hallucinations or critical issues"
        elif confidence_score < 0.6 or critical_issues > 0:
            risk_level = "MEDIUM"
            risk_color = "orange"
            risk_description = "Moderate risk with some validation concerns"
        elif medium_issues > 3:
            risk_level = "LOW-MEDIUM"
            risk_color = "yellow"
            risk_description = "Low to medium risk with multiple minor issues"
        else:
            risk_level = "LOW"
            risk_color = "green"
            risk_description = "Low risk, script appears well-validated"
        
        risk_factors = []
        if critical_issues > 0:
            risk_factors.append(f"{critical_issues} critical validation issues")
        if medium_issues > 0:
            risk_factors.append(f"{medium_issues} medium priority issues")
        if confidence_score < 0.7:
            risk_factors.append(f"Low confidence score ({confidence_score:.2f})")
        
        return {
            "level": risk_level,
            "color": risk_color,
            "description": risk_description,
            "factors": risk_factors,
            "recommendation": self._get_risk_recommendation(risk_level)
        }
    
    def _get_risk_recommendation(self, risk_level: str) -> str:
        """Get recommendation based on risk level."""
        recommendations = {
            "HIGH": "DO NOT USE - Requires significant review and fixes",
            "MEDIUM": "USE WITH CAUTION - Review and test thoroughly",
            "LOW-MEDIUM": "REVIEW RECOMMENDED - Minor issues should be addressed",
            "LOW": "APPROVED FOR USE - Consider adding tests"
        }
        return recommendations.get(risk_level, "Unknown risk level")
    
    def _generate_action_items(self, validation_result: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate specific action items for addressing issues."""
        action_items = []
        issues = validation_result.get("issues", [])
        
        for issue in issues:
            action_item = {
                "issue_type": issue.get("type", "unknown"),
                "component": issue.get("component", ""),
                "priority": issue.get("severity", "medium"),
                "description": issue.get("message", ""),
                "suggested_action": self._get_action_for_issue_type(issue.get("type", ""))
            }
            action_items.append(action_item)
        
        return action_items
    
    def _get_action_for_issue_type(self, issue_type: str) -> str:
        """Get suggested action for specific issue types."""
        actions = {
            "unknown_import": "Verify import exists and install dependency if needed",
            "suspicious_function": "Review function logic and test behavior manually",
            "unverified_external_call": "Check API documentation and test endpoint",
            "suspicious_file_operation": "Review file operations for security implications"
        }
        return actions.get(issue_type, "Review and validate manually")